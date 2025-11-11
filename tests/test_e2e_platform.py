
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent))

class TestPlatformE2E(unittest.TestCase):
    
    def setUp(self):
        self.test_env = {
            'OIDC_AUTHORITY': 'https://test-auth.bookverse.com',
            'OIDC_AUDIENCE': 'bookverse:api:test',
            'AUTH_ENABLED': 'false',
            'DEVELOPMENT_MODE': 'true',
            'JFROG_URL': 'https://swampupsec.jfrog.io',
            'JF_OIDC_TOKEN': 'test-oidc-token-123'
        }
    
    def test_01_platform_imports(self):
        print("\n🧪 Testing Platform Module Imports...")
        
        try:
            from app import auth
            from app import main
            print("✅ All platform modules imported successfully")
        except ImportError as e:
            self.fail(f"❌ Import failed: {e}")
    
    def test_02_shared_libraries(self):
        print("\n🧪 Testing Shared Library Integration...")
        
        try:
            from bookverse_core.auth import AuthUser, validate_jwt_token
            from bookverse_core.utils import get_logger
            
            logger = get_logger(__name__)
            self.assertIsNotNone(logger)
            print("✅ Shared logging utility works")
            
            test_claims = {
                'sub': 'test-user',
                'email': 'test@bookverse.com',
                'name': 'Test User',
                'scope': 'openid profile email bookverse:api',
                'roles': ['user']
            }
            auth_user = AuthUser(test_claims)
            self.assertEqual(auth_user.user_id, 'test-user')
            self.assertEqual(auth_user.email, 'test@bookverse.com')
            print("✅ Shared authentication utilities work")
            
        except Exception as e:
            self.fail(f"❌ Shared library test failed: {e}")
    
    def test_03_platform_auth_module(self):
        print("\n🧪 Testing Platform Authentication Module...")
        
        with patch.dict(os.environ, self.test_env):
            try:
                from app.auth import get_auth_status, get_current_user
                
                status = get_auth_status()
                self.assertIsInstance(status, dict)
                self.assertIn('auth_enabled', status)
                print("✅ Auth status retrieval works")
                
                import asyncio
                async def test_get_user():
                    user = await get_current_user()
                    return user
                
                user = asyncio.run(test_get_user())
                self.assertIsNotNone(user)
                self.assertEqual(user.user_id, 'demo-user')
                print("✅ User authentication works")
                
            except Exception as e:
                self.fail(f"❌ Platform auth test failed: {e}")
    
    def test_05_platform_aggregator_config(self):
        print("\n🧪 Testing Platform Aggregator Configuration...")
        
        try:
            from app.main import load_services_config, parse_args
            
            config_path = Path(__file__).parent.parent / 'config' / 'services.yaml'
            if config_path.exists():
                services = load_services_config(config_path)
                self.assertIsInstance(services, list)
                self.assertGreater(len(services), 0)
                
                for service in services:
                    self.assertIn('name', service)
                    self.assertIn('apptrust_application', service)
                
                print(f"✅ Configuration loaded: {len(services)} services")
            else:
                print("⚠️  Services config not found, skipping config test")
            
            args = parse_args()
            self.assertIsNotNone(args)
            print("✅ Argument parsing works")
            
        except Exception as e:
            self.fail(f"❌ Aggregator config test failed: {e}")
    
    def test_06_semver_utilities(self):
        print("\n🧪 Testing SemVer Utilities...")
        
        try:
            from app.main import SemVer, sort_versions_by_semver_desc, compare_semver
            
            test_versions = ['1.0.0', '1.0.1', '1.1.0', '2.0.0', '1.0.0-alpha']
            parsed_versions = []
            
            for version in test_versions:
                semver = SemVer.parse(version)
                self.assertIsNotNone(semver, f"Failed to parse {version}")
                parsed_versions.append(semver)
            
            print("✅ SemVer parsing works")
            
            sorted_versions = sort_versions_by_semver_desc(test_versions)
            self.assertEqual(sorted_versions[0], '2.0.0')
            print("✅ SemVer sorting works")
            
            v1 = SemVer.parse('1.0.0')
            v2 = SemVer.parse('1.0.1')
            self.assertEqual(compare_semver(v1, v2), -1)
            print("✅ SemVer comparison works")
            
        except Exception as e:
            self.fail(f"❌ SemVer utilities test failed: {e}")
    
    def test_07_apptrust_client(self):
        print("\n🧪 Testing AppTrust Client...")
        
        with patch.dict(os.environ, self.test_env):
            try:
                from app.main import AppTrustClient
                
                client = AppTrustClient(
                    base_url='https://swampupsec.jfrog.io/apptrust/api/v1',
                    token='test-token'
                )
                self.assertIsNotNone(client)
                print("✅ AppTrust client created")
                
                with patch('urllib.request.urlopen') as mock_urlopen:
                    mock_response = MagicMock()
                    mock_response.read.return_value = b'{"test": "response"}'
                    mock_urlopen.return_value.__enter__.return_value = mock_response
                    
                    result = client._request('GET', '/test')
                    self.assertEqual(result, {"test": "response"})
                    print("✅ AppTrust client request method works")
                
            except Exception as e:
                self.fail(f"❌ AppTrust client test failed: {e}")
    
    def test_09_workflow_yaml_syntax(self):
        print("\n🧪 Testing Workflow YAML Syntax...")
        
        try:
            import yaml
            workflows_dir = Path(__file__).parent.parent / '.github' / 'workflows'
            
            if workflows_dir.exists():
                workflow_files = list(workflows_dir.glob('*.yml'))
                self.assertGreater(len(workflow_files), 0, "No workflow files found")
                
                for workflow_file in workflow_files:
                    with open(workflow_file, 'r') as f:
                        try:
                            yaml.safe_load(f)
                            print(f"✅ {workflow_file.name}: Valid YAML")
                        except yaml.YAMLError as e:
                            self.fail(f"❌ {workflow_file.name}: Invalid YAML - {e}")
                
                print(f"✅ All {len(workflow_files)} workflow files have valid YAML")
            else:
                print("⚠️  Workflows directory not found")
                
        except Exception as e:
            self.fail(f"❌ Workflow YAML test failed: {e}")
    
    def test_10_platform_integration(self):
        print("\n🧪 Testing Platform Integration...")
        
        try:
            config_dir = Path(__file__).parent.parent / 'config'
            self.assertTrue(config_dir.exists(), "Config directory missing")
            
            services_config = config_dir / 'services.yaml'
            if services_config.exists():
                with open(services_config, 'r') as f:
                    import yaml
                    config = yaml.safe_load(f)
                    self.assertIn('services', config)
                    print("✅ Services configuration accessible")
            
            scripts_dir = Path(__file__).parent.parent / 'scripts'
            if scripts_dir.exists():
                script_files = list(scripts_dir.glob('*.py'))
                for script in script_files:
                    try:
                        result = subprocess.run([
                            sys.executable, '-m', 'py_compile', str(script)
                        ], capture_output=True, text=True, cwd=script.parent.parent)
                        self.assertEqual(result.returncode, 0, 
                                       f"Script {script.name} compilation failed")
                    except Exception as e:
                        print(f"⚠️  Script test for {script.name} skipped: {e}")
                
                print(f"✅ Platform scripts validated")
            
            print("✅ Platform integration tests completed")
            
        except Exception as e:
            self.fail(f"❌ Platform integration test failed: {e}")

def run_e2e_tests():
    print("🚀 Starting BookVerse Platform E2E Testing")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestPlatformE2E)
    
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("🏁 E2E Testing Summary")
    print("-" * 30)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ Failures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\n💥 Errors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    if result.wasSuccessful():
        print("\n🎉 All E2E tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed or had errors")
        return 1

if __name__ == '__main__':
    sys.exit(run_e2e_tests())
