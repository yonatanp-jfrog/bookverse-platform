#!/usr/bin/env python3
"""
Platform Tagging Service Functionality Tests
Tests the platform tagging service and lifecycle management.
"""

import os
import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add platform app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

class TestPlatformTagging(unittest.TestCase):
    """Test platform tagging functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_env = {
            'APPTRUST_BASE_URL': 'https://test.jfrog.io/apptrust/api/v1',
            'APPTRUST_ACCESS_TOKEN': 'test-token-123'
        }
        
        # Mock version data for testing
        self.mock_prod_versions = [
            {
                'version': '1.3.0',
                'release_status': 'RELEASED',
                'current_stage': 'PROD',
                'tag': 'latest'
            },
            {
                'version': '1.2.1',
                'release_status': 'RELEASED', 
                'current_stage': 'PROD',
                'tag': '1.2.1'
            },
            {
                'version': '1.2.0',
                'release_status': 'RELEASED',
                'current_stage': 'PROD', 
                'tag': '1.2.0'
            }
        ]
    
    def test_tagging_constants(self):
        """Test tagging service constants."""
        print("\n🧪 Testing Tagging Constants...")
        
        from app.tagging_service import (
            LATEST_TAG, QUARANTINE_TAG, BACKUP_BEFORE_LATEST,
            BACKUP_BEFORE_QUARANTINE, RELEASED, TRUSTED_RELEASE
        )
        
        self.assertEqual(LATEST_TAG, 'latest')
        self.assertEqual(QUARANTINE_TAG, 'quarantine')
        self.assertEqual(BACKUP_BEFORE_LATEST, 'original_tag_before_latest')
        self.assertEqual(BACKUP_BEFORE_QUARANTINE, 'original_tag_before_quarantine')
        self.assertEqual(RELEASED, 'RELEASED')
        self.assertEqual(TRUSTED_RELEASE, 'TRUSTED_RELEASE')
        
        print("✅ All tagging constants defined correctly")
    
    def test_version_sorting(self):
        """Test semantic version sorting for tagging."""
        print("\n🧪 Testing Version Sorting...")
        
        from app.tagging_service import sort_versions_by_semver_desc
        
        test_versions = ['1.0.0', '1.2.1', '1.3.0', '1.2.0', '2.0.0']
        sorted_versions = sort_versions_by_semver_desc(test_versions)
        
        expected_order = ['2.0.0', '1.3.0', '1.2.1', '1.2.0', '1.0.0']
        self.assertEqual(sorted_versions, expected_order)
        
        print("✅ Version sorting works correctly")
    
    def test_prod_version_filtering(self):
        """Test filtering of PROD versions."""
        print("\n🧪 Testing PROD Version Filtering...")
        
        from app.tagging_service import get_prod_versions, AppTrustClient
        
        # Mock client response
        with patch.dict(os.environ, self.test_env), \
             patch.object(AppTrustClient, 'list_application_versions') as mock_list:
            mock_list.return_value = {'versions': self.mock_prod_versions}
            
            client = AppTrustClient()
            
            async def test_filter():
                return await get_prod_versions(client, 'bookverse-inventory')
            
            prod_versions = asyncio.run(test_filter())
            
            # Should return all 3 versions as they all have RELEASED status and PROD stage
            self.assertEqual(len(prod_versions), 3)
            
            # Check that debug info was added
            for version in prod_versions:
                self.assertIn('_debug_included_reason', version)
            
            print("✅ PROD version filtering works")
    
    def test_latest_candidate_selection(self):
        """Test selection of next latest candidate."""
        print("\n🧪 Testing Latest Candidate Selection...")
        
        from app.tagging_service import pick_next_latest
        
        # Test normal case - exclude version 1.3.0, should pick 1.2.1
        async def test_selection():
            next_latest = await pick_next_latest(self.mock_prod_versions, '1.3.0')
            return next_latest
        
        result = asyncio.run(test_selection())
        self.assertIsNotNone(result)
        self.assertEqual(result['version'], '1.2.1')
        
        print("✅ Latest candidate selection works")
    
    def test_tagging_backup_logic(self):
        """Test tag backup and restoration logic."""
        print("\n🧪 Testing Tag Backup Logic...")
        
        from app.tagging_service import backup_tag_then_patch, AppTrustClient
        
        with patch.object(AppTrustClient, 'patch_application_version') as mock_patch:
            mock_patch.return_value = {'status': 'success'}
            
            client = AppTrustClient()
            
            async def test_backup():
                await backup_tag_then_patch(
                    client, 'bookverse-inventory', '1.2.1', 
                    'backup_key', 'latest', 'old-tag'
                )
            
            asyncio.run(test_backup())
            
            # Verify patch was called with correct parameters
            mock_patch.assert_called_once()
            call_args = mock_patch.call_args
            
            self.assertEqual(call_args[0][0], 'bookverse-inventory')  # app_key
            self.assertEqual(call_args[0][1], '1.2.1')  # version
            self.assertEqual(call_args[1]['tag'], 'latest')  # new tag
            self.assertIn('properties', call_args[1])
            
            print("✅ Tag backup logic works")
    
    def test_webhook_event_model(self):
        """Test webhook event data model."""
        print("\n🧪 Testing Webhook Event Model...")
        
        from app.tagging_service import WebhookEvent
        
        # Test valid webhook event
        event_data = {
            'app_key': 'bookverse-inventory',
            'version': '1.2.3',
            'event_type': 'promoted',
            'from_stage': 'STAGING',
            'to_stage': 'PROD'
        }
        
        event = WebhookEvent(**event_data)
        self.assertEqual(event.app_key, 'bookverse-inventory')
        self.assertEqual(event.version, '1.2.3')
        self.assertEqual(event.event_type, 'promoted')
        self.assertEqual(event.from_stage, 'STAGING')
        self.assertEqual(event.to_stage, 'PROD')
        
        print("✅ Webhook event model works")
    
    def test_fastapi_app_creation(self):
        """Test FastAPI application creation."""
        print("\n🧪 Testing FastAPI App Creation...")
        
        with patch.dict(os.environ, self.test_env):
            from app.tagging_service import app
            from fastapi import FastAPI
            
            self.assertIsInstance(app, FastAPI)
            self.assertEqual(app.title, "BookVerse Platform Tagging System")
            
            print("✅ FastAPI app creation works")
    
    def test_health_endpoints(self):
        """Test health check endpoints."""
        print("\n🧪 Testing Health Endpoints...")
        
        with patch.dict(os.environ, self.test_env):
            from app.tagging_service import health
            
            # Test basic health endpoint
            health_response = health()
            self.assertEqual(health_response, {"status": "ok"})
            
            print("✅ Health endpoints work")
    
    def test_apptrust_client_creation(self):
        """Test AppTrust client creation for tagging."""
        print("\n🧪 Testing AppTrust Client Creation...")
        
        with patch.dict(os.environ, self.test_env):
            from app.tagging_service import AppTrustClient
            
            client = AppTrustClient()
            self.assertEqual(client.base_url, 'https://test.jfrog.io/apptrust/api/v1')
            self.assertEqual(client.token, 'test-token-123')
            
            print("✅ AppTrust client creation works")
    
    def test_clear_quarantine_logic(self):
        """Test quarantine tag clearing logic."""
        print("\n🧪 Testing Quarantine Clearing Logic...")
        
        from app.tagging_service import clear_quarantine_tags_for_re_released_versions, AppTrustClient
        
        # Mock versions with quarantine tags
        mock_versions_with_quarantine = [
            {
                'version': '1.2.0',
                'release_status': 'RELEASED',
                'current_stage': 'PROD',
                'tag': 'quarantine-1.2.0',
                'properties': {
                    'original_tag_before_quarantine': ['1.2.0']
                }
            }
        ]
        
        with patch.object(AppTrustClient, 'patch_application_version') as mock_patch:
            mock_patch.return_value = {'status': 'success'}
            
            client = AppTrustClient()
            
            async def test_clear():
                await clear_quarantine_tags_for_re_released_versions(
                    client, 'bookverse-inventory', mock_versions_with_quarantine
                )
            
            asyncio.run(test_clear())
            
            # Verify patch was called to clear quarantine
            mock_patch.assert_called_once()
            call_args = mock_patch.call_args
            
            self.assertEqual(call_args[1]['tag'], '1.2.0')  # restored tag
            self.assertIn('delete_properties', call_args[1])
            
            print("✅ Quarantine clearing logic works")
    
    def test_enforce_latest_tag_mock(self):
        """Test latest tag enforcement with mocked data."""
        print("\n🧪 Testing Latest Tag Enforcement (Mock)...")
        
        from app.tagging_service import enforce_latest_tag_invariants, AppTrustClient
        
        # Mock all the dependencies
        with patch('app.tagging_service.get_prod_versions') as mock_get_prod, \
             patch('app.tagging_service.clear_quarantine_tags_for_re_released_versions') as mock_clear, \
             patch.object(AppTrustClient, 'patch_application_version') as mock_patch:
            
            # Setup mocks
            mock_get_prod.return_value = self.mock_prod_versions
            mock_clear.return_value = None
            mock_patch.return_value = {'status': 'success'}
            
            with patch.dict(os.environ, self.test_env):
                client = AppTrustClient()
                async def test_enforce():
                    await enforce_latest_tag_invariants(client, 'bookverse-inventory')
                
                asyncio.run(test_enforce())
                
                # Verify the functions were called
                mock_get_prod.assert_called_once()
                mock_clear.assert_called_once()
                
                print("✅ Latest tag enforcement works")

def run_tagging_tests():
    """Run tagging service tests."""
    print("🚀 Starting Platform Tagging Service Testing")
    print("=" * 55)
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestPlatformTagging)
    
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 55)
    print("🏁 Tagging Service Testing Summary")
    print("-" * 40)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n🎉 All tagging service tests passed!")
        return 0
    else:
        print("\n⚠️  Some tagging service tests failed")
        return 1

if __name__ == '__main__':
    sys.exit(run_tagging_tests())
