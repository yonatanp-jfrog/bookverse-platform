"""Platform tagging logic for version lifecycle management.

This module handles the automatic tagging logic to ensure:
- The latest semver version in prod always has the 'latest' tag
- Versions that lose 'latest' due to newer versions get their original tag back
- Rolled back versions get quarantine tags
- When the latest version is rolled back, the next latest becomes latest
"""

import os
from typing import Dict, List, Optional, Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import httpx

# Import shared libraries
from bookverse_core.utils import get_logger

# Import authentication module
from . import auth

# Use shared logging
logger = get_logger(__name__)

app = FastAPI(title="BookVerse Platform Tagging System")

# Constants
LATEST_TAG = "latest"
QUARANTINE_TAG = "quarantine"
BACKUP_BEFORE_LATEST = "original_tag_before_latest"
BACKUP_BEFORE_QUARANTINE = "original_tag_before_quarantine"
RELEASED = "RELEASED"
TRUSTED_RELEASE = "TRUSTED_RELEASE"


class WebhookEvent(BaseModel):
    """AppTrust webhook event structure"""
    app_key: str
    version: str
    event_type: str  # "promoted", "rollback", "tagged"
    from_stage: Optional[str] = None
    to_stage: Optional[str] = None
    new_tag: Optional[str] = None
    previous_tag: Optional[str] = None


class AppTrustClient:
    """Simplified AppTrust API client for tagging operations"""
    
    def __init__(self):
        self.base_url = os.getenv("APPTRUST_BASE_URL", "").rstrip('/')
        self.token = os.getenv("APPTRUST_ACCESS_TOKEN", "")
        if not self.base_url or not self.token:
            raise ValueError("APPTRUST_BASE_URL and APPTRUST_ACCESS_TOKEN must be set")
    
    async def list_application_versions(self, app_key: str, limit: int = 1000) -> Dict[str, Any]:
        """List all versions for an application"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/applications/{quote(app_key)}/versions"
            headers = {"Authorization": f"Bearer {self.token}"}
            params = {"limit": limit, "order_by": "created", "order_asc": "false"}
            
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
    
    async def patch_application_version(
        self, 
        app_key: str, 
        version: str, 
        tag: Optional[str] = None,
        properties: Optional[Dict[str, List[str]]] = None,
        delete_properties: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Update version tag and/or properties"""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/applications/{quote(app_key)}/versions/{quote(version)}"
            headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
            
            body: Dict[str, Any] = {}
            if tag is not None:
                body["tag"] = tag
            if properties is not None:
                body["properties"] = properties
            if delete_properties is not None:
                body["delete_properties"] = delete_properties
            
            response = await client.patch(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()


async def get_prod_versions(client: AppTrustClient, app_key: str) -> List[Dict[str, Any]]:
    """Get all versions that are truly in PROD (both stage=PROD AND status=RELEASED/TRUSTED_RELEASE)"""
    response = await client.list_application_versions(app_key)
    versions = response.get("versions", [])
    
    prod_versions = []
    for version in versions:
        release_status = str(version.get("release_status", "")).upper()
        current_stage = str(version.get("current_stage", "")).upper()
        
        # A version is truly "in prod" only if BOTH conditions are met:
        # 1. Current stage is PROD
        # 2. Release status is RELEASED or TRUSTED_RELEASE
        is_truly_in_prod = (
            current_stage == "PROD" and 
            release_status in [RELEASED, TRUSTED_RELEASE]
        )
        
        if is_truly_in_prod:
            # Add debug info for better troubleshooting
            version_info = {
                **version,
                "_debug_included_reason": f"truly_in_prod (stage={current_stage}, status={release_status})"
            }
            prod_versions.append(version_info)
    
    return prod_versions


def sort_versions_by_semver_desc(versions: List[str]) -> List[str]:
    """Sort versions by semantic version in descending order"""
    def semver_key(version: str):
        try:
            parts = version.split('.')
            return tuple(int(part) for part in parts)
        except ValueError:
            # If not a valid semver, put it at the end
            return (0, 0, 0)
    
    return sorted(versions, key=semver_key, reverse=True)


async def pick_next_latest(
    prod_versions: List[Dict[str, Any]], 
    exclude_version: str
) -> Optional[Dict[str, Any]]:
    """Pick the next latest version excluding quarantined and target version"""
    candidates = []
    
    for version in prod_versions:
        if version["version"] == exclude_version:
            continue
        
        tag = version.get("tag", "")
        if tag.startswith("quarantine") or tag.startswith("Quarantine"):
            continue
        
        candidates.append(version)
    
    if not candidates:
        return None
    
    # Sort by semver and return the highest
    versions_only = [v["version"] for v in candidates]
    sorted_versions = sort_versions_by_semver_desc(versions_only)
    
    if not sorted_versions:
        return None
    
    # Find the candidate with the highest version
    target_version = sorted_versions[0]
    for candidate in candidates:
        if candidate["version"] == target_version:
            return candidate
    
    return None


async def backup_tag_then_patch(
    client: AppTrustClient,
    app_key: str,
    version: str,
    backup_prop_key: str,
    new_tag: str,
    current_tag: str
) -> None:
    """Back up current tag to properties and set new tag"""
    properties = {backup_prop_key: [current_tag]} if current_tag else {}
    
    await client.patch_application_version(
        app_key, 
        version, 
        tag=new_tag, 
        properties=properties if current_tag else None
    )


async def clear_quarantine_tags_for_re_released_versions(
    client: AppTrustClient,
    app_key: str,
    prod_versions: List[Dict[str, Any]]
) -> None:
    """Clear quarantine tags from versions that have been re-released to prod"""
    
    for version in prod_versions:
        tag = version.get("tag", "")
        version_str = version["version"]
        
        # If version is in prod but still has quarantine tag, clear it
        if tag.startswith("quarantine"):
            logger.info(f"Clearing quarantine tag from re-released version {version_str}")
            
            # Get original tag from backup properties
            original_tag = version_str  # Default fallback
            properties = version.get("properties", {})
            
            if BACKUP_BEFORE_QUARANTINE in properties:
                backup_tags = properties[BACKUP_BEFORE_QUARANTINE]
                if backup_tags and isinstance(backup_tags, list):
                    original_tag = backup_tags[0]
            
            # Restore original tag and clear quarantine backup
            await client.patch_application_version(
                app_key,
                version_str,
                tag=original_tag,
                delete_properties=[BACKUP_BEFORE_QUARANTINE]
            )
            
            logger.info(f"Restored tag '{original_tag}' to re-released version {version_str}")
            
            # Update the version object for subsequent processing
            version["tag"] = original_tag


async def enforce_latest_tag_invariants(client: AppTrustClient, app_key: str) -> None:
    """Ensure the highest semver version in prod has the latest tag"""
    logger.info(f"Enforcing latest tag invariants for {app_key}")
    
    prod_versions = await get_prod_versions(client, app_key)
    
    if not prod_versions:
        logger.info(f"No prod versions found for {app_key}")
        return
    
    # Log all prod versions for debugging
    logger.info(f"Found {len(prod_versions)} prod versions:")
    for v in prod_versions:
        tag = v.get("tag", "")
        stage = v.get("current_stage", "")
        status = v.get("release_status", "")
        logger.info(f"  {v['version']}: tag='{tag}', stage='{stage}', status='{status}'")
    
    # SPECIAL CASE: Handle re-released versions that still have quarantine tags
    # If a version is back in prod (RELEASED status) but still has a quarantine tag,
    # we should clear the quarantine tag and restore its original tag
    await clear_quarantine_tags_for_re_released_versions(client, app_key, prod_versions)
    
    # Find the highest semver version (excluding currently quarantined)
    # NOTE: A version that was previously quarantined but is now back in prod 
    # (has RELEASED status) should be considered for latest tag
    currently_quarantined = []
    eligible_for_latest = []
    
    for v in prod_versions:
        tag = v.get("tag", "")
        if tag.startswith("quarantine"):
            currently_quarantined.append(v)
            logger.info(f"  {v['version']}: Still quarantined (tag: {tag})")
        else:
            eligible_for_latest.append(v)
    
    logger.info(f"Currently quarantined versions: {[v['version'] for v in currently_quarantined]}")
    logger.info(f"Eligible for latest: {[v['version'] for v in eligible_for_latest]}")
    
    if not eligible_for_latest:
        logger.warning(f"No non-quarantined versions found for {app_key}")
        return
    
    versions_only = [v["version"] for v in eligible_for_latest]
    sorted_versions = sort_versions_by_semver_desc(versions_only)
    logger.info(f"Sorted versions: {sorted_versions}")
    
    if not sorted_versions:
        logger.warning(f"No valid versions found for {app_key}")
        return
    
    desired_latest = sorted_versions[0]
    logger.info(f"Desired latest version: {desired_latest}")
    
    # Find current version with latest tag
    current_latest = None
    for version in prod_versions:
        if version.get("tag") == LATEST_TAG:
            current_latest = version
            break
    
    if current_latest:
        logger.info(f"Current latest version: {current_latest['version']}")
    else:
        logger.info("No version currently has latest tag")
    
    # If the desired latest already has the latest tag, we're done
    if current_latest and current_latest["version"] == desired_latest:
        logger.info(f"Latest tag already correctly assigned to {desired_latest}")
        return
    
    # Find the desired version object
    desired_version_obj = None
    for version in prod_versions:
        if version["version"] == desired_latest:
            desired_version_obj = version
            break
    
    if not desired_version_obj:
        logger.error(f"Could not find version object for {desired_latest}")
        return
    
    # Backup current tag and assign latest to desired version
    current_tag = desired_version_obj.get("tag", "")
    await backup_tag_then_patch(
        client,
        app_key,
        desired_latest,
        BACKUP_BEFORE_LATEST,
        LATEST_TAG,
        current_tag
    )
    
    logger.info(f"Assigned latest tag to {desired_latest}")
    
    # Restore original tag to previous latest version
    if current_latest and current_latest["version"] != desired_latest:
        old_version = current_latest["version"]
        
        # Get the original tag from properties or default to version
        original_tag = "version"
        properties = current_latest.get("properties", {})
        if BACKUP_BEFORE_LATEST in properties:
            original_tags = properties[BACKUP_BEFORE_LATEST]
            if original_tags and isinstance(original_tags, list):
                original_tag = original_tags[0]
        
        # If original tag is empty or same as latest, use version as fallback
        if not original_tag or original_tag == LATEST_TAG:
            original_tag = old_version
        
        await client.patch_application_version(
            app_key,
            old_version,
            tag=original_tag,
            delete_properties=[BACKUP_BEFORE_LATEST]
        )
        
        logger.info(f"Restored tag '{original_tag}' to previous latest version {old_version}")


async def handle_rollback_tagging(
    client: AppTrustClient,
    app_key: str,
    target_version: str
) -> None:
    """Handle tagging logic when a version is rolled back"""
    logger.info(f"Handling rollback tagging for {app_key}@{target_version}")
    
    prod_versions = await get_prod_versions(client, app_key)
    
    # Find the target version
    target_version_obj = None
    for version in prod_versions:
        if version["version"] == target_version:
            target_version_obj = version
            break
    
    if not target_version_obj:
        logger.error(f"Target version {target_version} not found in prod versions")
        return
    
    current_tag = target_version_obj.get("tag", "")
    had_latest = current_tag == LATEST_TAG
    
    # Step 1: Apply quarantine tag with backup
    quarantine_tag = f"quarantine-{target_version}"
    await backup_tag_then_patch(
        client,
        app_key,
        target_version,
        BACKUP_BEFORE_QUARANTINE,
        quarantine_tag,
        current_tag
    )
    
    logger.info(f"Applied quarantine tag to {target_version}")
    
    # Step 2: If it had latest tag, promote next latest
    if had_latest:
        next_candidate = await pick_next_latest(prod_versions, target_version)
        
        if next_candidate is None:
            logger.warning(f"No successor found for latest tag after rolling back {target_version}")
            return
        
        candidate_version = next_candidate["version"]
        candidate_tag = next_candidate.get("tag", "")
        
        await backup_tag_then_patch(
            client,
            app_key,
            candidate_version,
            BACKUP_BEFORE_LATEST,
            LATEST_TAG,
            candidate_tag
        )
        
        logger.info(f"Promoted {candidate_version} to latest after rollback")
    else:
        logger.info(f"Rolled back non-latest version {target_version}; latest tag unchanged")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/health/auth")
def auth_health() -> Dict[str, Any]:
    """Get authentication service health and status"""
    return auth.get_auth_status()


@app.get("/health/auth/test")
async def auth_connection_test() -> Dict[str, Any]:
    """Test authentication service connectivity"""
    return await auth.test_auth_connection()


@app.post("/webhook/apptrust")
async def handle_apptrust_webhook(
    event: WebhookEvent,
    background_tasks: BackgroundTasks,
    user: auth.AuthUser = auth.RequireApiScope
) -> Dict[str, str]:
    """Handle AppTrust webhook events for tagging logic"""
    logger.info(f"Received webhook event: {event.dict()}")
    
    try:
        client = AppTrustClient()
        
        if event.event_type == "promoted" and event.to_stage == "PROD":
            # Version was promoted to PROD - enforce latest tag invariants
            background_tasks.add_task(
                enforce_latest_tag_invariants,
                client,
                event.app_key
            )
            
        elif event.event_type == "rollback":
            # Version was rolled back - handle quarantine tagging
            background_tasks.add_task(
                handle_rollback_tagging,
                client,
                event.app_key,
                event.version
            )
            
        return {"status": "accepted"}
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/enforce-tagging/{app_key}")
async def enforce_tagging_manually(
    app_key: str,
    background_tasks: BackgroundTasks,
    user: auth.AuthUser = auth.RequireAuth
) -> Dict[str, str]:
    """Manually trigger tag enforcement for an application"""
    logger.info(f"Manual tag enforcement requested for {app_key}")
    
    try:
        client = AppTrustClient()
        background_tasks.add_task(
            enforce_latest_tag_invariants,
            client,
            app_key
        )
        return {"status": "enforcement_scheduled"}
        
    except Exception as e:
        logger.error(f"Error scheduling tag enforcement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


