#!/usr/bin/env bash

# =============================================================================
# EXPAND PLATFORM OIDC PERMISSIONS SCRIPT
# =============================================================================
# Expands the platform OIDC provider's identity mapping to include permissions
# for all service applications, fixing the HTTP 403 authorization issue.
# =============================================================================

set -euo pipefail

# Configuration
PROJECT_KEY="${PROJECT_KEY:-bookverse}"
JFROG_URL="${JFROG_URL:-https://apptrustswampupc.jfrog.io}"
JFROG_ADMIN_TOKEN="${JFROG_ADMIN_TOKEN:-}"
ORG="${ORG:-yonatanp-jfrog}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Validate required environment
validate_environment() {
    if [[ -z "$JFROG_ADMIN_TOKEN" ]]; then
        log_error "JFROG_ADMIN_TOKEN environment variable is required"
        exit 1
    fi
    
    if [[ -z "$JFROG_URL" ]]; then
        log_error "JFROG_URL environment variable is required"
        exit 1
    fi
    
    if [[ -z "$PROJECT_KEY" ]]; then
        log_error "PROJECT_KEY environment variable is required"
        exit 1
    fi
}

# Check if identity mapping exists
mapping_exists() {
    local integration_name="$1"
    local mapping_name="$2"
    local tmp=$(mktemp)
    local code
    
    code=$(curl -s \
        --header "Authorization: Bearer ${JFROG_ADMIN_TOKEN}" \
        --header "Accept: application/json" \
        -w "%{http_code}" -o "$tmp" \
        "${JFROG_URL}/access/api/v1/oidc/${integration_name}/identity_mappings" 2>/dev/null || echo "000")
    
    if [[ "$code" -ge 200 && "$code" -lt 300 ]]; then
        if grep -q "\"name\"[[:space:]]*:[[:space:]]*\"${mapping_name}\"" "$tmp" 2>/dev/null; then
            rm -f "$tmp"
            return 0
        fi
    fi
    rm -f "$tmp"
    return 1
}

# Create cross-service identity mapping for platform
create_platform_cross_service_mapping() {
    local platform_integration="bookverse-platform-github"
    local mapping_name="platform-cross-service-access"
    
    log_info "Creating cross-service identity mapping for platform OIDC provider"
    log_info "Integration: $platform_integration"
    log_info "Mapping: $mapping_name"
    
    # Check if mapping already exists
    if mapping_exists "$platform_integration" "$mapping_name"; then
        log_warning "Cross-service mapping '$mapping_name' already exists"
        return 0
    fi
    
    # Build identity mapping payload that grants access to ALL service repositories
    # This allows the platform to access bookverse-inventory, bookverse-recommendations, etc.
    local mapping_payload
    mapping_payload=$(jq -n \
        --arg name "$mapping_name" \
        --arg priority "10" \
        --arg repo_pattern "${ORG}/bookverse-*" \
        --arg scope "applied-permissions/roles:${PROJECT_KEY}:cicd_pipeline" \
        '{
            "name": $name,
            "description": "Cross-service access for platform aggregation and management",
            "priority": ($priority | tonumber),
            "claims": {
                "repository": $repo_pattern
            },
            "token_spec": {
                "scope": $scope
            }
        }')
    
    log_info "Identity mapping payload:"
    echo "$mapping_payload" | jq .
    
    # Create the mapping
    local temp_response=$(mktemp)
    local response_code
    
    response_code=$(curl -s \
        --header "Authorization: Bearer ${JFROG_ADMIN_TOKEN}" \
        --header "Content-Type: application/json" \
        -X POST \
        -d "$mapping_payload" \
        --write-out "%{http_code}" \
        --output "$temp_response" \
        "${JFROG_URL}/access/api/v1/oidc/${platform_integration}/identity_mappings")
    
    case "$response_code" in
        200|201)
            log_success "Cross-service identity mapping created successfully"
            rm -f "$temp_response"
            return 0
            ;;
        409)
            log_warning "Cross-service identity mapping already exists (HTTP $response_code)"
            rm -f "$temp_response"
            return 0
            ;;
        *)
            log_error "Failed to create cross-service identity mapping (HTTP $response_code)"
            log_error "Response: $(cat "$temp_response")"
            rm -f "$temp_response"
            return 1
            ;;
    esac
}

# Alternative approach: Create specific mappings for each service repository
create_specific_service_mappings() {
    local platform_integration="bookverse-platform-github"
    local services=("inventory" "recommendations" "checkout" "web")
    
    log_info "Creating specific service mappings for platform OIDC provider"
    
    for service in "${services[@]}"; do
        local mapping_name="platform-access-${service}"
        
        if mapping_exists "$platform_integration" "$mapping_name"; then
            log_warning "Service mapping '$mapping_name' already exists"
            continue
        fi
        
        log_info "Creating mapping for service: $service"
        
        local mapping_payload
        mapping_payload=$(jq -n \
            --arg name "$mapping_name" \
            --arg priority "5" \
            --arg repo "${ORG}/bookverse-${service}" \
            --arg scope "applied-permissions/roles:${PROJECT_KEY}:cicd_pipeline" \
            '{
                "name": $name,
                "description": ("Platform access to " + $service + " service"),
                "priority": ($priority | tonumber),
                "claims": {
                    "repository": $repo
                },
                "token_spec": {
                    "scope": $scope
                }
            }')
        
        local temp_response=$(mktemp)
        local response_code
        
        response_code=$(curl -s \
            --header "Authorization: Bearer ${JFROG_ADMIN_TOKEN}" \
            --header "Content-Type: application/json" \
            -X POST \
            -d "$mapping_payload" \
            --write-out "%{http_code}" \
            --output "$temp_response" \
            "${JFROG_URL}/access/api/v1/oidc/${platform_integration}/identity_mappings")
        
        case "$response_code" in
            200|201)
                log_success "Service mapping for '$service' created successfully"
                ;;
            409)
                log_warning "Service mapping for '$service' already exists"
                ;;
            *)
                log_error "Failed to create service mapping for '$service' (HTTP $response_code)"
                log_error "Response: $(cat "$temp_response")"
                ;;
        esac
        
        rm -f "$temp_response"
    done
}

# List current identity mappings for platform
list_platform_mappings() {
    local platform_integration="bookverse-platform-github"
    
    log_info "Current identity mappings for $platform_integration:"
    
    local temp_response=$(mktemp)
    local response_code
    
    response_code=$(curl -s \
        --header "Authorization: Bearer ${JFROG_ADMIN_TOKEN}" \
        --header "Accept: application/json" \
        -w "%{http_code}" -o "$temp_response" \
        "${JFROG_URL}/access/api/v1/oidc/${platform_integration}/identity_mappings")
    
    if [[ "$response_code" -ge 200 && "$response_code" -lt 300 ]]; then
        cat "$temp_response" | jq '.[]? | {name: .name, priority: .priority, repository: .claims.repository, scope: .token_spec.scope}' 2>/dev/null || cat "$temp_response"
    else
        log_error "Failed to list identity mappings (HTTP $response_code)"
        cat "$temp_response"
    fi
    
    rm -f "$temp_response"
}

# Main execution
main() {
    echo ""
    log_info "🚀 Expanding Platform OIDC Permissions"
    log_info "🔧 Project: $PROJECT_KEY"
    log_info "🔧 JFrog URL: $JFROG_URL"
    log_info "🔧 Organization: $ORG"
    echo ""
    
    validate_environment
    
    log_info "📋 Current platform identity mappings:"
    list_platform_mappings
    echo ""
    
    log_info "🔧 Creating cross-service access mappings..."
    
    # Try cross-service wildcard mapping first
    if create_platform_cross_service_mapping; then
        log_success "Cross-service mapping approach successful"
    else
        log_warning "Cross-service mapping failed, trying specific service mappings..."
        create_specific_service_mappings
    fi
    
    echo ""
    log_info "📋 Updated platform identity mappings:"
    list_platform_mappings
    
    echo ""
    log_success "🎉 Platform OIDC permissions expansion completed!"
    log_info "The platform should now have access to all service applications"
    log_info "This fixes the HTTP 403 authorization issue in platform aggregation"
    echo ""
}

# Handle script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
