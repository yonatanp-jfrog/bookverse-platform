#!/bin/bash

# Test script to validate the OIDC permissions fix
# This can be run within a GitHub Actions workflow context

set -euo pipefail

echo "🧪 Testing OIDC Permissions Fix"
echo "================================"

# Check if we have the required environment variables
if [[ -z "${JFROG_ADMIN_TOKEN:-}" ]]; then
    echo "❌ Missing JFROG_ADMIN_TOKEN - cannot test OIDC fix"
    exit 1
fi

if [[ -z "${JFROG_URL:-}" ]]; then
    echo "❌ Missing JFROG_URL - cannot test OIDC fix"
    exit 1
fi

PROJECT_KEY="${PROJECT_KEY:-bookverse}"
PLATFORM_INTEGRATION="bookverse-platform-github"

echo "Project: $PROJECT_KEY"
echo "JFrog URL: $JFROG_URL"
echo "Platform Integration: $PLATFORM_INTEGRATION"
echo ""

# Test 1: Check current identity mappings
echo "📋 Current platform identity mappings:"
MAPPINGS=$(curl -sS -H "Authorization: Bearer ${JFROG_ADMIN_TOKEN}" \
    -H "Accept: application/json" \
    "${JFROG_URL}/access/api/v1/oidc/${PLATFORM_INTEGRATION}/identity_mappings" || echo '[]')

echo "$MAPPINGS" | jq -r '.[]? | "  - " + .name + " -> " + (.claims.repository // "N/A")' || echo "No mappings found"
echo ""

# Test 2: Check if cross-service access exists
echo "🔍 Checking for cross-service access..."
if echo "$MAPPINGS" | jq -e '.[]? | select(.claims.repository | test("bookverse-\\*$"))' >/dev/null 2>&1; then
    echo "✅ Cross-service access already configured"
    NEEDS_FIX=false
else
    echo "❌ Cross-service access not found"
    NEEDS_FIX=true
fi
echo ""

# Test 3: Try to access a service application
echo "🧪 Testing access to bookverse-inventory application..."
INVENTORY_RESP=$(curl -sS -H "Authorization: Bearer ${JFROG_ADMIN_TOKEN}" \
    -H "Accept: application/json" \
    "${JFROG_URL}/apptrust/api/v1/applications/bookverse-inventory/versions?limit=1" 2>/dev/null || echo '{"error": "failed"}')

if echo "$INVENTORY_RESP" | jq -e '.versions' >/dev/null 2>&1; then
    echo "✅ Successfully accessed bookverse-inventory"
    VERSION_COUNT=$(echo "$INVENTORY_RESP" | jq '.versions | length')
    echo "   Found $VERSION_COUNT versions"
    HAS_ACCESS=true
elif echo "$INVENTORY_RESP" | jq -e '.error' >/dev/null 2>&1 || [[ "$INVENTORY_RESP" == *"403"* ]] || [[ "$INVENTORY_RESP" == *"Forbidden"* ]]; then
    echo "❌ Access denied (HTTP 403) - confirms the authorization issue"
    HAS_ACCESS=false
else
    echo "⚠️  Unexpected response:"
    echo "$INVENTORY_RESP" | head -200
    HAS_ACCESS=false
fi
echo ""

# Summary and recommendation
echo "🏁 OIDC Permissions Analysis Summary"
echo "===================================="
echo "Cross-service mapping configured: $(!$NEEDS_FIX && echo "Yes" || echo "No")"
echo "Has access to service apps: $($HAS_ACCESS && echo "Yes" || echo "No")"
echo ""

if [[ "$NEEDS_FIX" == "true" ]]; then
    echo "🔧 RECOMMENDATION: Apply OIDC permissions fix"
    echo "   Run: ./scripts/expand-platform-oidc-permissions.sh"
    echo "   This will create cross-service identity mappings"
elif [[ "$HAS_ACCESS" == "false" ]]; then
    echo "⚠️  INVESTIGATION NEEDED: Cross-service mapping exists but access still denied"
    echo "   This may indicate a different authorization issue"
    echo "   Check: Role permissions, application existence, token scope"
else
    echo "✅ OIDC permissions are correctly configured"
    echo "   Platform has proper access to service applications"
fi

echo ""
echo "🎯 This analysis helps identify the root cause of HTTP 403 errors"
