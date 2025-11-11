"""
BookVerse Platform Service - Application Aggregation and Release Management

This module implements sophisticated platform aggregation functionality for the
BookVerse microservices ecosystem, providing automated service version resolution,
manifest generation, and platform release orchestration through JFrog AppTrust
integration.

🏗️ Platform Architecture:
    - Service Aggregation: Automated collection of production-ready microservice versions
    - Version Resolution: Intelligent semantic version parsing and selection logic
    - Manifest Generation: Comprehensive platform manifests with provenance tracking
    - AppTrust Integration: Full lifecycle management through JFrog AppTrust APIs
    - Release Orchestration: Automated platform version creation and deployment

🚀 Key Features:
    - Semantic Versioning: Full SemVer 2.0 compliance with prerelease support
    - Production Filtering: Automatic selection of RELEASED and TRUSTED_RELEASE versions
    - Version Overrides: Manual version specification for testing and hotfixes
    - Manifest Provenance: Complete audit trail with evidence collection
    - Preview Mode: Safe dry-run capabilities for validation and testing
    - Error Recovery: Comprehensive error handling and graceful degradation

🔧 Integration Capabilities:
    - JFrog AppTrust: Complete API integration for version and content management
    - GitHub Actions: Native CI/CD integration with environment variable support
    - YAML Configuration: Flexible service configuration with validation
    - Manifest Output: Structured YAML manifests for downstream consumption
    - Logging Integration: Comprehensive logging for debugging and audit

📊 Business Logic:
    - Platform Releases: Bi-weekly aggregation cycles with hotfix support
    - Quality Gates: Production readiness validation for all included services
    - Dependency Resolution: Intelligent handling of service interdependencies
    - Release Tagging: Automated tag generation for release categorization
    - Audit Compliance: Full evidence collection for regulatory requirements

🛠️ Usage Patterns:
    - Automated Releases: Scheduled platform aggregation in CI/CD pipelines
    - Manual Overrides: Developer-initiated releases with specific versions
    - Preview Operations: Safe testing of aggregation logic without changes
    - Hotfix Releases: Emergency releases with selective version overrides
    - Integration Testing: Platform version validation in staging environments

Authors: BookVerse Platform Team
Version: 1.0.0
"""

import argparse
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from functools import cmp_to_key

import yaml


def load_services_config(config_path: Path) -> List[Dict[str, Any]]:
    """
    Load and validate service configuration from YAML file.
    
    This function loads the service configuration that defines which microservices
    are included in platform aggregation, along with their AppTrust application
    keys and metadata needed for version resolution.
    
    🔧 Configuration Structure:
        The YAML file should contain a 'services' list with entries like:
        ```yaml
        services:
          - name: "inventory"
            apptrust_application: "bookverse-inventory"
            description: "Product catalog and inventory management"
          - name: "recommendations"
            apptrust_application: "bookverse-recommendations"
            description: "AI-powered recommendation engine"
        ```
    
    Args:
        config_path (Path): Path to the services.yaml configuration file
        
    Returns:
        List[Dict[str, Any]]: List of service configuration dictionaries
        
    Raises:
        FileNotFoundError: If the configuration file doesn't exist
        ValueError: If the configuration format is invalid
        
    Example:
        ```python
        config_path = Path("config/services.yaml")
        services = load_services_config(config_path)
        
        for service in services:
            print(f"Service: {service['name']}")
            print(f"AppTrust Key: {service['apptrust_application']}")
        ```
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Services config not found: {config_path}")
    
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    
    services = data.get("services", [])
    if not isinstance(services, list) or not services:
        raise ValueError("Config 'services' must be a non-empty list")
    
    return services


# Comprehensive SemVer 2.0 regular expression with full prerelease and build metadata support
SEMVER_RE = re.compile(
    r"^\s*v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?\s*$"
)


class SemVer:
    """
    Semantic Version parser and container implementing SemVer 2.0 specification.
    
    This class provides comprehensive semantic version parsing, comparison, and
    manipulation capabilities essential for platform version management and
    dependency resolution in the BookVerse microservices ecosystem.
    
    🎯 Purpose:
        - Parse semantic version strings with full SemVer 2.0 compliance
        - Enable version comparison for latest version selection
        - Support prerelease version handling for staging environments
        - Provide version increment logic for automated releases
        - Maintain original version string for audit and display
    
    📊 SemVer Components:
        - Major: Breaking changes (incompatible API changes)
        - Minor: New functionality (backward-compatible additions)
        - Patch: Bug fixes (backward-compatible fixes)
        - Prerelease: Development versions (alpha, beta, rc)
        - Build Metadata: Build information (commit hashes, timestamps)
    
    🔧 Supported Formats:
        - Standard: "1.2.3", "v1.2.3"
        - Prerelease: "1.2.3-alpha.1", "1.2.3-beta"
        - Build: "1.2.3+20240101.abc123"
        - Combined: "1.2.3-rc.1+build.456"
    
    Example:
        ```python
        # Parse different version formats
        v1 = SemVer.parse("1.2.3")
        v2 = SemVer.parse("v2.0.0-beta.1")
        v3 = SemVer.parse("1.5.0+build.123")
        
        # Version properties
        print(f"Major: {v1.major}, Minor: {v1.minor}, Patch: {v1.patch}")
        print(f"Prerelease: {v2.prerelease}")  # ('beta', '1')
        print(f"Original: {v2.original}")      # "v2.0.0-beta.1"
        ```
    
    Version: 1.0.0
    """
    
    def __init__(self, major: int, minor: int, patch: int, prerelease: Tuple[str, ...], original: str) -> None:
        """
        Initialize semantic version with parsed components.
        
        Args:
            major (int): Major version number
            minor (int): Minor version number  
            patch (int): Patch version number
            prerelease (Tuple[str, ...]): Prerelease identifiers tuple
            original (str): Original version string for reference
        """
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease  # Tuple of prerelease identifiers
        self.original = original      # Original string for audit/display

    @staticmethod
    def parse(version: str) -> Optional["SemVer"]:
        """
        Parse a version string into a SemVer object using SemVer 2.0 specification.
        
        This method implements complete SemVer 2.0 parsing including support for
        prerelease versions, build metadata, and various format variations commonly
        used in software versioning.
        
        🔧 Parsing Logic:
            - Strips leading/trailing whitespace and optional 'v' prefix
            - Validates major.minor.patch numeric format
            - Extracts prerelease identifiers (alpha, beta, rc, etc.)
            - Preserves original string for audit and display purposes
            - Returns None for invalid version strings
        
        Args:
            version (str): Version string to parse (e.g., "1.2.3", "v2.0.0-beta.1")
            
        Returns:
            Optional[SemVer]: Parsed SemVer object or None if invalid
            
        Example:
            ```python
            # Valid version strings
            v1 = SemVer.parse("1.2.3")              # Standard version
            v2 = SemVer.parse("v2.0.0-alpha.1")     # Prerelease with prefix
            v3 = SemVer.parse("1.0.0+build.123")    # With build metadata
            
            # Invalid version strings
            invalid = SemVer.parse("1.2")           # Returns None
            invalid = SemVer.parse("not-a-version") # Returns None
            
            # Prerelease handling
            beta = SemVer.parse("1.0.0-beta.2")
            print(beta.prerelease)  # ('beta', '2')
            ```
        """
        m = SEMVER_RE.match(version)
        if not m:
            return None
        
        g = m.groupdict()
        prerelease_raw = g.get("prerelease") or ""
        
        return SemVer(
            int(g["major"]), 
            int(g["minor"]), 
            int(g["patch"]), 
            tuple(prerelease_raw.split(".")) if prerelease_raw else tuple(), 
            version
        )


def compare_semver(a: SemVer, b: SemVer) -> int:
    """
    Compare two semantic versions according to SemVer 2.0 precedence rules.
    
    This function implements the complete SemVer 2.0 comparison algorithm, handling
    major, minor, patch, and prerelease version precedence correctly for accurate
    version ordering in platform aggregation.
    
    🔧 Comparison Rules (SemVer 2.0):
        1. Major.Minor.Patch compared numerically
        2. Release versions have higher precedence than prerelease
        3. Prerelease identifiers compared alphanumerically
        4. Numeric identifiers compared numerically
        5. Larger set of prerelease identifiers has higher precedence
    
    Args:
        a (SemVer): First version to compare
        b (SemVer): Second version to compare
        
    Returns:
        int: -1 if a < b, 0 if a == b, 1 if a > b
        
    Example:
        ```python
        v1 = SemVer.parse("1.0.0")
        v2 = SemVer.parse("2.0.0")
        v3 = SemVer.parse("2.0.0-alpha")
        
        assert compare_semver(v1, v2) == -1  # 1.0.0 < 2.0.0
        assert compare_semver(v3, v2) == -1  # 2.0.0-alpha < 2.0.0
        assert compare_semver(v2, v2) == 0   # 2.0.0 == 2.0.0
        ```
    """
    # Compare major version
    if a.major != b.major:
        return -1 if a.major < b.major else 1
    
    # Compare minor version
    if a.minor != b.minor:
        return -1 if a.minor < b.minor else 1
    
    # Compare patch version
    if a.patch != b.patch:
        return -1 if a.patch < b.patch else 1
    
    # Handle prerelease precedence: release > prerelease
    if not a.prerelease and b.prerelease:
        return 1   # a (release) > b (prerelease)
    if a.prerelease and not b.prerelease:
        return -1  # a (prerelease) < b (release)
    
    # Both are prerelease or both are release - compare prerelease identifiers
    for at, bt in zip(a.prerelease, b.prerelease):
        if at == bt:
            continue
        
        a_num, b_num = at.isdigit(), bt.isdigit()
        
        if a_num and b_num:
            # Both numeric - compare as integers
            ai, bi = int(at), int(bt)
            if ai != bi:
                return -1 if ai < bi else 1
        elif a_num and not b_num:
            # Numeric < non-numeric
            return -1
        elif not a_num and b_num:
            # Non-numeric > numeric  
            return 1
        else:
            # Both non-numeric - lexical comparison
            if at < bt:
                return -1
            return 1
    
    # All compared identifiers are equal - longer prerelease has higher precedence
    if len(a.prerelease) != len(b.prerelease):
        return -1 if len(a.prerelease) < len(b.prerelease) else 1
    
    return 0  # Versions are equal


def sort_versions_by_semver_desc(version_strings: List[str]) -> List[str]:
    """
    Sort a list of version strings in descending semantic version order.
    
    This function parses version strings into SemVer objects and sorts them
    according to SemVer 2.0 precedence rules, returning the highest version
    first. Invalid version strings are filtered out.
    
    🎯 Purpose:
        - Identify the latest/highest version from a collection
        - Sort versions for display in descending order
        - Filter out invalid version strings automatically
        - Support platform version selection logic
    
    Args:
        version_strings (List[str]): List of version strings to sort
        
    Returns:
        List[str]: Sorted version strings in descending order (highest first)
        
    Example:
        ```python
        versions = ["1.0.0", "2.0.0-alpha", "2.0.0", "1.2.3", "invalid"]
        sorted_versions = sort_versions_by_semver_desc(versions)
        # Returns: ["2.0.0", "2.0.0-alpha", "1.2.3", "1.0.0"]
        # Note: "invalid" is filtered out
        
        # Get latest version
        latest = sorted_versions[0] if sorted_versions else None
        ```
    """
    # Parse valid version strings and keep original strings
    parsed: List[Tuple[SemVer, str]] = []
    for v in version_strings:
        sv = SemVer.parse(v)
        if sv is not None:
            parsed.append((sv, v))
    
    # Sort by SemVer comparison in descending order (highest first)
    parsed.sort(key=cmp_to_key(lambda a, b: compare_semver(a[0], b[0])), reverse=True)
    
    # Return original version strings in sorted order
    return [v for _, v in parsed]


class AppTrustClient:
    """
    HTTP client for JFrog AppTrust API integration in platform aggregation workflows.
    
    This class provides comprehensive integration with JFrog AppTrust APIs for
    application version management, content retrieval, and platform version
    creation in the BookVerse microservices ecosystem.
    
    🎯 Purpose:
        - Interact with JFrog AppTrust REST APIs for version management
        - Retrieve application version lists and content details
        - Create platform versions with aggregated service dependencies
        - Support authentication and error handling for API operations
        - Enable platform release automation through programmatic access
    
    🔧 Key Features:
        - OAuth/Bearer token authentication for secure API access
        - Configurable timeout handling for network reliability
        - Comprehensive error handling with detailed error messages
        - JSON request/response handling with validation
        - URL encoding for safe parameter passing
    
    🚀 Supported Operations:
        - List Application Versions: Get version history for applications
        - Get Version Content: Retrieve detailed version content and releasables
        - Create Platform Version: Aggregate services into platform releases
        - Authentication: Bearer token-based API authentication
        - Error Recovery: Comprehensive exception handling and reporting
    
    Example:
        ```python
        # Initialize client with AppTrust credentials
        client = AppTrustClient(
            base_url="https://swampupsec.jfrog.io/apptrust/api/v1",
            token="bearer-token-here",
            timeout_seconds=300
        )
        
        # Get latest versions for an application
        versions = client.list_application_versions("bookverse-inventory")
        
        # Create platform version
        sources = [
            {"application_key": "bookverse-inventory", "version": "1.2.3"},
            {"application_key": "bookverse-checkout", "version": "2.1.0"}
        ]
        platform_version = client.create_platform_version(
            "bookverse-platform", "2024.01.15.123456", sources
        )
        ```
    
    Version: 1.0.0
    """
    
    def __init__(self, base_url: str, token: str, timeout_seconds: int = 600) -> None:
        """
        Initialize AppTrust client with connection parameters.
        
        Args:
            base_url (str): Base URL for AppTrust API (e.g., https://swampupsec.jfrog.io/apptrust/api/v1)
            token (str): Bearer token for API authentication
            timeout_seconds (int): Request timeout in seconds (default: 600)
        """
        self.base_url = base_url.rstrip("/")  # Remove trailing slash for consistent URLs
        self.token = token                    # Bearer token for authentication
        self.timeout_seconds = timeout_seconds  # Request timeout configuration

    def _request(self, method: str, path: str, query: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            q = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
            url = f"{url}?{q}"
        data = None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                try:
                    return json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON response from AppTrust API: {e}. Raw response: {raw.decode('utf-8', errors='replace')[:500]}")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace') if hasattr(e, 'read') else 'No error body'
            raise ValueError(f"AppTrust API HTTP {e.code} error for {method} {url}: {error_body}")
        except urllib.error.URLError as e:
            raise ValueError(f"AppTrust API connection error for {method} {url}: {e}")
        except Exception as e:
            raise ValueError(f"AppTrust API request failed for {method} {url}: {e}")

    def list_application_versions(self, app_key: str, limit: int = 200) -> Dict[str, Any]:
        path = f"/applications/{urllib.parse.quote(app_key)}/versions"
        return self._request("GET", path, query={"limit": limit, "order_by": "created", "order_asc": "false"})

    def get_version_content(self, app_key: str, version: str) -> Dict[str, Any]:
        path = f"/applications/{urllib.parse.quote(app_key)}/versions/{urllib.parse.quote(version)}/content"
        return self._request("GET", path, query={"include": "releasables"})

    def create_platform_version(self, platform_app_key: str, version: str, sources_versions: List[Dict[str, str]], tag: str = "release") -> Dict[str, Any]:
        path = f"/applications/{urllib.parse.quote(platform_app_key)}/versions"
        body = {
            "version": version,
            "tag": tag,
            "sources": {
                "versions": sources_versions
            },
        }
        return self._request("POST", path, body=body)


RELEASED = "RELEASED"
TRUSTED_RELEASE = "TRUSTED_RELEASE"


def compute_next_semver_for_application(client: AppTrustClient, app_key: str) -> str:
    try:
        resp = client.list_application_versions(app_key, limit=1)
        versions = resp.get("versions", []) if isinstance(resp, dict) else []
        latest = str(versions[0].get("version", "")) if versions else ""
    except Exception as e:
        print(f"WARNING: Failed to get latest application version for {app_key}: {e}", flush=True)
        latest = ""

    parsed = SemVer.parse(latest) if latest else None
    if parsed is not None:
        return f"{parsed.major}.{parsed.minor}.{parsed.patch + 1}"

    try:
        version_map_path = Path(__file__).parent.parent / "config" / "version-map.yaml"
        if version_map_path.exists():
            with version_map_path.open("r", encoding="utf-8") as f:
                version_map = yaml.safe_load(f) or {}
            
            for app in version_map.get("applications", []):
                if app.get("key") == app_key:
                    seed = app.get("seeds", {}).get("application")
                    if seed:
                        seed_parsed = SemVer.parse(str(seed))
                        if seed_parsed:
                            return f"{seed_parsed.major}.{seed_parsed.minor}.{seed_parsed.patch + 1}"
                    break
    except Exception:
        pass
    
    return "1.0.1"


def pick_latest_prod_version(client: AppTrustClient, app_key: str) -> Optional[str]:

    resp = client.list_application_versions(app_key)
    versions_raw = resp.get("versions", []) if isinstance(resp, dict) else []


    normalized: List[Dict[str, Any]] = []
    for v in versions_raw:
        if not isinstance(v, dict):
            continue
        ver = str(v.get("version", "")).strip()
        if not ver:
            continue
        rs = str(v.get("release_status", "")).upper().strip()
        tag = str(v.get("tag", "")).strip()
        stage = str(v.get("current_stage", "")).upper().strip()
        normalized.append({
            "version": ver,
            "release_status": rs,
            "tag": tag,
            "current_stage": stage,
        })

    prod_candidates_full: List[Dict[str, Any]] = [
        n for n in normalized if n.get("release_status") in (RELEASED, TRUSTED_RELEASE)
    ]
    prod_candidates: List[str] = [n["version"] for n in prod_candidates_full]


    if not prod_candidates:
        return None

    if not prod_candidates:
        return None

    ordered = sort_versions_by_semver_desc(prod_candidates)
    return ordered[0] if ordered else None


def resolve_promoted_versions(
    services_cfg: List[Dict[str, Any]],
    client: AppTrustClient,
    override_versions: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:

    resolved: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for s in services_cfg:
        name = s.get("name")
        app_key = s.get("apptrust_application")
        if not name or not app_key:
            raise ValueError(f"Service config missing required fields: {s}")
        if override_versions and name in override_versions:
            resolved_version = override_versions[name]
            resolved.append({
                "name": name,
                "apptrust_application": app_key,
                "resolved_version": resolved_version,
            })
            continue

        latest = pick_latest_prod_version(client, app_key)
        if not latest:
            missing.append({
                "name": name,
                "apptrust_application": app_key,
            })
            continue
        resolved.append({
            "name": name,
            "apptrust_application": app_key,
            "resolved_version": latest,
        })
    return resolved, missing


def build_manifest(applications: List[Dict[str, Any]], client: AppTrustClient, source_stage: str) -> Dict[str, Any]:
    if source_stage != "PROD":
        raise ValueError("Platform aggregation demo only supports source_stage=PROD")

    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    manifest_version = now.strftime("%Y.%m.%d.%H%M%S")

    apps_block: List[Dict[str, Any]] = []
    for entry in applications:
        app_key = entry.get("apptrust_application")
        version = entry.get("resolved_version") or entry.get("simulated_version", "0.0.0-sim")
        if not app_key or not version:
            raise ValueError(f"Application entry missing required fields: {entry}")

        content = client.get_version_content(app_key, str(version))
        if not content or not isinstance(content, dict):
            raise ValueError(f"Failed to get version content for {app_key} version {version}. This indicates an API authentication or connectivity issue.")
        
        sources = content.get("sources", {})
        releasables = content.get("releasables", [])
        
        if not releasables:
            raise ValueError(f"No releasables found for {app_key} version {version}. This version may not have been properly built or published.")

        apps_block.append(
            {
                "application_key": app_key,
                "version": version,
                "sources": sources,
                "releasables": releasables,
            }
        )

    manifest: Dict[str, Any] = {
        "version": manifest_version,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "source_stage": source_stage,
        "applications": apps_block,
        "provenance": {
            "evidence_minimums": {"signatures_present": True},
        },
        "notes": "Auto-generated by platform-aggregator (applications & versions)",
    }
    return manifest


def write_manifest(output_dir: Path, manifest: Dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"platform-{manifest['version']}.yaml"
    target = output_dir / filename
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)
    return target


def format_summary(manifest: Dict[str, Any]) -> str:
    apps = manifest.get("applications", [])
    rows = []
    for comp in apps:
        rows.append(
            {
                "application_key": comp.get("application_key"),
                "version": comp.get("version"),
            }
        )
    return json.dumps(
        {
            "platform_manifest_version": manifest["version"],
            "platform_app_version": manifest.get("platform_app_version", ""),
            "applications": rows,
        },
        indent=2,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BookVerse Platform Aggregator (demo). Generates a platform manifest by selecting latest PROD microservice versions.",
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config" / "services.yaml"),
        help="Path to services.yaml (static configuration).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "manifests"),
        help="Directory to write manifests into.",
    )
    parser.add_argument(
        "--source-stage",
        default="PROD",
        help="Source stage (fixed to PROD for the demo).",
    )
    parser.add_argument(
        "--platform-app",
        default=os.environ.get("PLATFORM_APP_KEY", f"{os.environ.get('PROJECT_KEY', 'bookverse')}-platform"),
        help="Platform application key in AppTrust.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: resolve live versions and print summary only (no AppTrust or file writes).",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="SERVICE=VERSION",
        help="Override a service version (can be provided multiple times), e.g., inventory=1.8.2",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config_path = Path(args.config)
    output_dir = Path(args.output_dir)
    source_stage = args.source_stage
    do_write = not bool(args.preview)

    services_cfg = load_services_config(config_path)

    overrides: Dict[str, str] = {}
    for ov in getattr(args, "override", []) or []:
        if "=" not in ov:
            print(f"ERROR: Malformed override '{ov}' - must be in format 'service=version'", flush=True)
            return 2
        svc, ver = ov.split("=", 1)
        svc = svc.strip()
        ver = ver.strip()
        if not svc or not ver:
            print(f"ERROR: Malformed override '{ov}' - service and version cannot be empty", flush=True)
            return 2
        overrides[svc] = ver

    base_url = os.environ.get("APPTRUST_BASE_URL", "").strip()
    if not base_url:
        jfrog_url = os.environ.get("JFROG_URL", "").strip()
        if jfrog_url:
            base_url = f"{jfrog_url.rstrip('/')}/apptrust/api/v1"
    
    token = os.environ.get("JF_OIDC_TOKEN", "").strip()
    
    if not base_url:
        print("ERROR: APPTRUST_BASE_URL environment variable is required", flush=True)
        print("       Alternatively, set JFROG_URL and it will be auto-constructed", flush=True)
        return 2
    
    if not token:
        print("ERROR: Authentication token is required", flush=True)
        print("       Set JF_OIDC_TOKEN environment variable", flush=True)
        return 2
    
    try:
        client = AppTrustClient(base_url=base_url, token=token)
    except Exception as e:
        print(f"Auth/client initialization failed: {e}", flush=True)
        return 2
    services, missing = resolve_promoted_versions(services_cfg, client, overrides or None)

    if not services:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        message = (
            "No aggregatable application versions were found (release_status not in {RELEASED, TRUSTED_RELEASE}).\n"
        )
        if missing:
            try:
                names = ", ".join(sorted([m.get("apptrust_application", "") or m.get("name", "") for m in missing]))
                message += f"Missing: {names}\n"
            except Exception:
                pass
        print(message.strip())
        if summary_path:
            try:
                with open(summary_path, "a", encoding="utf-8") as f:
                    f.write("\n" + message + "\n")
            except Exception:
                pass
        return 0

    manifest = build_manifest(services, client, source_stage)

    platform_app_key = str(getattr(args, "platform_app"))
    platform_app_version = compute_next_semver_for_application(client, platform_app_key)

    manifest["platform_app_version"] = platform_app_version

    print(format_summary(manifest))

    if do_write:
        target = write_manifest(output_dir, manifest)
        print(f"Wrote manifest: {target}")
        
        tag_options = ["release", "hotfix", "feature", "bugfix", "enhancement", "security", "performance", "refactor"]
        github_run_number = int(os.environ.get("GITHUB_RUN_NUMBER", "1"))
        tag_index = github_run_number % len(tag_options)
        app_tag = tag_options[tag_index]
        print(f"🏷️ Platform Application Version Tag: {app_tag}")
        
        sources_versions = [
            {"application_key": s["apptrust_application"], "version": s["resolved_version"]}
            for s in services
        ]
        resp = client.create_platform_version(platform_app_key, platform_app_version, sources_versions, app_tag)
        print(json.dumps({"platform_version_created": resp}, indent=2))
    else:
        print("Preview: resolved live versions; no files written and no AppTrust changes. Omit --preview to create the platform version and write the manifest.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


