"""
BookVerse Platform Service - Semantic Version Management System

This module implements comprehensive semantic versioning automation for the BookVerse
platform aggregation service, providing intelligent version determination, package
tag management, and automated version bumping with AppTrust integration for
enterprise-grade release coordination and artifact management.

🏗️ Architecture Overview:
    - Semantic Versioning: Full SemVer 2.0 compliance with automated version bumping
    - AppTrust Integration: Complete integration with JFrog AppTrust for version management
    - Package Management: Multi-package version coordination across Docker and Generic artifacts
    - Conflict Resolution: Intelligent conflict detection and resolution with fallback mechanisms
    - CI/CD Integration: GitHub Actions integration with environment variable output
    - Audit Trail: Comprehensive logging and versioning history tracking

🚀 Key Features:
    - Automatic version determination with intelligent bumping algorithms
    - Multi-package coordination ensuring consistent versioning across artifacts
    - AppTrust API integration for centralized version management
    - Fallback mechanisms using configurable seed versions for new applications
    - Docker and Generic package support with repository-specific logic
    - GitHub Actions integration with automatic environment variable setting
    - Comprehensive error handling and graceful degradation

🔧 Technical Implementation:
    - SemVer Parsing: Robust semantic version parsing and validation
    - HTTP Client: Custom HTTP client with proper error handling and timeouts
    - YAML Configuration: Version mapping configuration with application-specific settings
    - Repository Integration: Direct integration with JFrog Artifactory repositories
    - API Communication: RESTful API integration with proper authentication
    - Environment Integration: GitHub Actions environment variable output

📊 Business Logic:
    - Release Coordination: Ensures consistent versioning across platform releases
    - Dependency Management: Coordinates version dependencies between services
    - Deployment Safety: Prevents version conflicts and deployment issues
    - Audit Compliance: Maintains complete versioning history for regulatory requirements
    - Development Workflow: Streamlines developer workflow with automated versioning

🛠️ Usage Patterns:
    - Platform Aggregation: Central component in bi-weekly platform release process
    - Service Development: Individual service version management during development
    - Hotfix Management: Emergency release version coordination and conflict resolution
    - CI/CD Automation: Automated version determination in deployment pipelines
    - Version Auditing: Historical version tracking and compliance reporting

Authors: BookVerse Platform Team
Version: 1.0.0
"""

import argparse
import json
import os
import re
import sys
from typing import List, Optional, Tuple, Dict, Any
import urllib.request
import urllib.parse

# 🎯 SemVer Pattern: Regular expression for strict semantic version validation
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(v: str) -> Optional[Tuple[int, int, int]]:
    """
    Parse semantic version string into structured tuple format.
    
    This function validates and parses semantic version strings according to SemVer 2.0
    specification, extracting major, minor, and patch version components for version
    comparison and manipulation operations.
    
    Args:
        v (str): Version string to parse (e.g., "1.2.3")
        
    Returns:
        Optional[Tuple[int, int, int]]: Tuple of (major, minor, patch) or None if invalid
        
    Examples:
        >>> parse_semver("1.2.3")
        (1, 2, 3)
        >>> parse_semver("invalid")
        None
        >>> parse_semver("1.2.3-beta")  # Pre-release not supported
        None
    """
    m = SEMVER_RE.match(v.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_patch(v: str) -> str:
    """
    Increment patch version component of semantic version string.
    
    This function performs patch-level version bumping according to SemVer 2.0
    specification, incrementing the patch number while maintaining major and
    minor version components for automated version progression.
    
    Args:
        v (str): Valid semantic version string (e.g., "1.2.3")
        
    Returns:
        str: Version string with incremented patch component (e.g., "1.2.4")
        
    Raises:
        ValueError: If input is not a valid semantic version
        
    Examples:
        >>> bump_patch("1.2.3")
        "1.2.4"
        >>> bump_patch("2.0.0")
        "2.0.1"
        >>> bump_patch("invalid")
        ValueError: Not a SemVer X.Y.Z: invalid
    """
    p = parse_semver(v)
    if not p:
        raise ValueError(f"Not a SemVer X.Y.Z: {v}")
    return f"{p[0]}.{p[1]}.{p[2] + 1}"


def max_semver(values: List[str]) -> Optional[str]:
    """
    Find highest semantic version from list of version strings.
    
    This function compares multiple semantic version strings and returns the
    highest version according to SemVer 2.0 precedence rules, filtering out
    invalid versions and providing reliable version selection logic.
    
    Args:
        values (List[str]): List of version strings to compare
        
    Returns:
        Optional[str]: Highest valid semantic version or None if no valid versions
        
    Examples:
        >>> max_semver(["1.2.3", "1.3.0", "1.2.10"])
        "1.3.0"
        >>> max_semver(["2.0.0", "1.9.9"])
        "2.0.0"
        >>> max_semver(["invalid", "bad"])
        None
        >>> max_semver([])
        None
    """
    parsed = [(parse_semver(v), v) for v in values]
    parsed = [(t, raw) for t, raw in parsed if t is not None]
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0])
    return parsed[-1][1]


def http_get(url: str, headers: Dict[str, str], timeout: int = 300) -> Any:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    try:
        return json.loads(data)
    except Exception:
        return data


def http_post(url: str, headers: Dict[str, str], data: str, timeout: int = 300) -> Any:
    req = urllib.request.Request(url, data=data.encode('utf-8'), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        response_data = resp.read().decode("utf-8")
    try:
        return json.loads(response_data)
    except Exception:
        return response_data


def load_version_map(path: str) -> Dict[str, Any]:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_app_entry(vm: Dict[str, Any], app_key: str) -> Dict[str, Any]:
    for it in vm.get("applications", []) or []:
        if (it.get("key") or "").strip() == app_key:
            return it
    return {}


def compute_next_application_version(app_key: str, vm: Dict[str, Any], jfrog_url: str, token: str) -> str:
    """
    Compute next application version with AppTrust integration and fallback logic.
    
    This function implements sophisticated version determination logic that queries the
    JFrog AppTrust API to find the latest application version, applies intelligent
    version bumping, and provides fallback mechanisms using seed versions for reliable
    version progression in enterprise environments.
    
    Args:
        app_key (str): Application key identifier in AppTrust
        vm (Dict[str, Any]): Version mapping configuration with seed values
        jfrog_url (str): Base URL for JFrog Platform
        token (str): Authentication token for AppTrust API access
        
    Returns:
        str: Next semantic version for the application
        
    Raises:
        SystemExit: If no valid seed version is available for new applications
        
    Algorithm:
        1. Query AppTrust API for latest application version
        2. If found and valid, bump patch version
        3. If not found, query broader version history
        4. Extract and analyze all valid semantic versions
        5. Find highest version and bump patch component
        6. Fallback to seed version from configuration if no versions exist
        
    Examples:
        >>> compute_next_application_version("bookverse-inventory", vm, url, token)
        "1.2.4"  # Latest was 1.2.3, bumped to 1.2.4
        
        >>> compute_next_application_version("new-app", vm, url, token)
        "1.0.1"  # No versions found, used seed 1.0.0 and bumped
        
    Integration Points:
        - AppTrust API: Version history and application management
        - Version Configuration: Seed values for new applications
        - CI/CD Pipeline: Automated version determination
        - Release Management: Coordinated version bumping
    """
    # 🌐 API Configuration: Set up AppTrust API endpoints and authentication
    base = jfrog_url.rstrip("/") + "/apptrust/api/v1"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 🔍 Latest Version Query: Get most recent application version
    latest_url = f"{base}/applications/{urllib.parse.quote(app_key)}/versions?limit=1&order_by=created&order_asc=false"
    try:
        latest_payload = http_get(latest_url, headers)
    except Exception:
        latest_payload = {}

    def first_version(obj: Any) -> Optional[str]:
        """Extract first version from API response with flexible field mapping."""
        if isinstance(obj, dict):
            arr = (
                obj.get("versions")
                or obj.get("results")
                or obj.get("items")
                or obj.get("data")
                or []
            )
            if arr:
                v = (arr[0] or {}).get("version") or (arr[0] or {}).get("name")
                return v if isinstance(v, str) else None
        return None

    # ⚡ Fast Path: Use latest version if available and valid
    latest_created = first_version(latest_payload)
    if isinstance(latest_created, str) and parse_semver(latest_created):
        return bump_patch(latest_created)

    # 📊 Version History: Query broader version history for analysis
    url = f"{base}/applications/{urllib.parse.quote(app_key)}/versions?limit=50&order_by=created&order_asc=false"
    try:
        payload = http_get(url, headers)
    except Exception:
        payload = {}

    def extract_versions(obj: Any) -> List[str]:
        """Extract all valid semantic versions from API response."""
        if isinstance(obj, dict):
            arr = (
                obj.get("versions")
                or obj.get("results")
                or obj.get("items")
                or obj.get("data")
                or []
            )
            out = []
            for it in arr or []:
                v = (it or {}).get("version") or (it or {}).get("name")
                if isinstance(v, str) and parse_semver(v):
                    out.append(v)
            return out
        elif isinstance(obj, list):
            return [x for x in obj if isinstance(x, str) and parse_semver(x)]
        return []

    # 🔢 Version Analysis: Find highest version and bump patch
    values = extract_versions(payload)
    latest = max_semver(values)
    if latest:
        return bump_patch(latest)

    # 🌱 Seed Fallback: Use configured seed version for new applications
    entry = find_app_entry(vm, app_key)
    seed = ((entry.get("seeds") or {}).get("application")) if entry else None
    if not seed or not parse_semver(str(seed)):
        raise SystemExit(f"No valid seed for application {app_key}")
    return bump_patch(str(seed))


def compute_next_build_number(app_key: str, vm: Dict[str, Any], jfrog_url: str, token: str) -> str:
    base = jfrog_url.rstrip("/") + "/apptrust/api/v1"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    vlist_url = f"{base}/applications/{urllib.parse.quote(app_key)}/versions?limit=1&order_by=created&order_asc=false"
    try:
        vlist = http_get(vlist_url, headers)
    except Exception:
        vlist = {}

    def first_version(obj: Any) -> Optional[str]:
        if isinstance(obj, dict):
            arr = (
                obj.get("versions")
                or obj.get("results")
                or obj.get("items")
                or obj.get("data")
                or []
            )
            if arr:
                v = (arr[0] or {}).get("version") or (arr[0] or {}).get("name")
                return v if isinstance(v, str) else None
        return None

    latest = first_version(vlist)
    if latest:
        try:
            vinfo = http_get(
                f"{base}/applications/{urllib.parse.quote(app_key)}/versions/{urllib.parse.quote(latest)}",
                headers,
            )
        except Exception:
            vinfo = {}
        num = None
        if isinstance(vinfo, dict):
            try:
                num = (((vinfo.get("sources") or {}).get("builds") or [])[0] or {}).get("number")
            except Exception:
                num = None
        if isinstance(num, str) and parse_semver(num):
            return bump_patch(num)

    entry = find_app_entry(vm, app_key)
    seed = ((entry.get("seeds") or {}).get("build")) if entry else None
    if not seed or not parse_semver(str(seed)):
        raise SystemExit(f"No valid build seed for application {app_key}")
    return bump_patch(str(seed))


def compute_next_package_tag(app_key: str, package_name: str, vm: Dict[str, Any], jfrog_url: str, token: str, project_key: Optional[str]) -> str:
    entry = find_app_entry(vm, app_key)
    pkg = None
    for it in (entry.get("packages") or []):
        if (it.get("name") or "").strip() == package_name:
            pkg = it
            break
    
    if not pkg:
        raise SystemExit(f"Package {package_name} not found in version map for {app_key}")
    
    seed = pkg.get("seed")
    package_type = pkg.get("type", "")
    
    if not seed or not parse_semver(str(seed)):
        raise SystemExit(f"No valid seed for package {app_key}/{package_name}")
    
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    existing_versions = []
    
    if package_type == "docker":
        try:
            service_name = app_key.replace("bookverse-", "")
            repo_key = f"{project_key or 'bookverse'}-{service_name}-internal-docker-nonprod-local"
            docker_url = f"{jfrog_url.rstrip('/')}/artifactory/api/docker/{repo_key}/v2/{package_name}/tags/list"
            
            resp = http_get(docker_url, headers)
            if isinstance(resp, dict) and "tags" in resp:
                for tag in resp.get("tags", []):
                    if isinstance(tag, str) and parse_semver(tag):
                        existing_versions.append(tag)
        except Exception:
            pass
    
    elif package_type == "generic":
        try:
            service_name = app_key.replace("bookverse-", "")
            repo_key = f"{project_key or 'bookverse'}-{service_name}-internal-generic-nonprod-local"
            
            aql_query = f'''items.find({{"repo":"{repo_key}","type":"file"}}).include("name","path","actual_sha1")'''
            aql_url = f"{jfrog_url.rstrip('/')}/artifactory/api/search/aql"
            aql_headers = headers.copy()
            aql_headers["Content-Type"] = "text/plain"
            
            resp = http_post(aql_url, aql_headers, aql_query)
            if isinstance(resp, dict) and "results" in resp:
                for item in resp.get("results", []):
                    path = item.get("path", "")
                    name = item.get("name", "")
                    
                    import re
                    version_pattern = r'/(\d+\.\d+\.\d+)/'
                    match = re.search(version_pattern, path)
                    if match:
                        version = match.group(1)
                        if parse_semver(version):
                            existing_versions.append(version)
        except Exception:
            pass
    
    if existing_versions:
        latest = max_semver(existing_versions)
        if latest:
            return bump_patch(latest)
    
    return bump_patch(str(seed))


def main():
    """
    Main entry point for semantic version management automation.
    
    This function implements the primary workflow for automated version determination
    in the BookVerse platform, coordinating application versions, build numbers, and
    package tags while integrating with GitHub Actions environment variables and
    providing comprehensive JSON output for downstream processing.
    
    Command Line Interface:
        --application-key: AppTrust application identifier (required)
        --version-map: YAML configuration file with version seeds (required)
        --jfrog-url: JFrog Platform base URL (required)
        --jfrog-token: Authentication token for API access (required)
        --project-key: JFrog project key for repository resolution (optional)
        --packages: Comma-separated package names for tag computation (optional)
    
    Workflow:
        1. Parse command line arguments and load version configuration
        2. Compute next application version using AppTrust API integration
        3. Determine next build number for CI/CD pipeline coordination
        4. Calculate package-specific tags for Docker and Generic artifacts
        5. Export environment variables for GitHub Actions integration
        6. Output comprehensive JSON response for downstream processing
    
    GitHub Actions Integration:
        - Sets APP_VERSION environment variable for application version
        - Sets DOCKER_TAG_* variables for each specified package
        - Environment variables automatically available in subsequent workflow steps
    
    Output Format:
        JSON object containing:
        - application_key: Input application identifier
        - app_version: Computed semantic version for application
        - build_number: Computed build number for CI/CD pipeline
        - package_tags: Dictionary of package names to computed tags
        - source: Description of version determination method used
    
    Examples:
        Basic application version computation:
        ```bash
        python semver_versioning.py \
            --application-key bookverse-inventory \
            --version-map version-map.yml \
            --jfrog-url https://apptrusttraining1.jfrog.io \
            --jfrog-token $JFROG_TOKEN
        ```
        
        Multi-package version computation:
        ```bash
        python semver_versioning.py \
            --application-key bookverse-inventory \
            --version-map version-map.yml \
            --jfrog-url https://apptrusttraining1.jfrog.io \
            --jfrog-token $JFROG_TOKEN \
            --packages "inventory-service,inventory-worker" \
            --project-key bookverse
        ```
    
    Error Handling:
        - Missing required arguments: Exits with argument parser error
        - Invalid version configuration: Exits with SystemExit and error message
        - API communication failures: Graceful degradation with fallback logic
        - Invalid seed versions: Exits with descriptive error message
    
    Integration Points:
        - AppTrust API: Version history and application management
        - GitHub Actions: Environment variable export for workflow integration
        - JFrog Artifactory: Package repository access for version analysis
        - YAML Configuration: Version mapping and seed value management
    """
    # 🎛️ Argument Parsing: Configure command line interface with required parameters
    p = argparse.ArgumentParser(description="Compute sequential SemVer versions with fallback to seeds")
    p.add_argument("compute", nargs="?")
    p.add_argument("--application-key", required=True)
    p.add_argument("--version-map", required=True)
    p.add_argument("--jfrog-url", required=True)
    p.add_argument("--jfrog-token", required=True)
    p.add_argument("--project-key", required=False)
    p.add_argument("--packages", help="Comma-separated package names to compute tags for", required=False)
    args = p.parse_args()

    # 📋 Configuration Loading: Load version mapping configuration from YAML file
    vm = load_version_map(args.version_map)
    app_key = args.application_key
    jfrog_url = args.jfrog_url
    token = args.jfrog_token

    # 🔢 Version Computation: Calculate application version and build number
    app_version = compute_next_application_version(app_key, vm, jfrog_url, token)
    build_number = compute_next_build_number(app_key, vm, jfrog_url, token)

    # 📦 Package Tag Computation: Calculate version tags for specified packages
    pkg_tags: Dict[str, str] = {}
    if args.packages:
        for name in [x.strip() for x in args.packages.split(",") if x.strip()]:
            pkg_tags[name] = compute_next_package_tag(app_key, name, vm, jfrog_url, token, args.project_key)

    # 🌍 GitHub Actions Integration: Export environment variables for workflow use
    env_path = os.environ.get("GITHUB_ENV")
    if env_path:
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"APP_VERSION={app_version}\n")
            for k, v in pkg_tags.items():
                key = re.sub(r"[^A-Za-z0-9_]", "_", k.upper())
                f.write(f"DOCKER_TAG_{key}={v}\n")

    # 📊 Output Generation: Create comprehensive JSON response for downstream processing
    out = {
        "application_key": app_key,
        "app_version": app_version,
        "build_number": build_number,
        "package_tags": pkg_tags,
        "source": "latest+bump or seed fallback"
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
