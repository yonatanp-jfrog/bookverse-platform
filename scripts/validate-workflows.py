#!/usr/bin/env python3
"""
Platform Workflow Validation Script
Validates that platform workflows maintain their core functionality after Phase 2 migration.
"""

import os
import sys
import yaml
from pathlib import Path

def validate_workflow_file(workflow_path):
    """Validate a single workflow file."""
    try:
        with open(workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)
        
        print(f"✅ {workflow_path.name}: Valid YAML")
        
        # Check for required platform-specific elements
        jobs = workflow.get('jobs', {})
        
        # Check for platform aggregation logic preservation
        if 'aggregate' in workflow_path.name:
            if any('python -m app.main' in str(job) for job in jobs.values()):
                print(f"  ✅ Platform aggregation logic preserved")
            else:
                print(f"  ⚠️  Platform aggregation logic not found")
        
        # Check for shared workflow usage
        shared_auth_found = False
        for job_name, job_config in jobs.items():
            if isinstance(job_config, dict) and job_config.get('uses', '').endswith('shared-platform-auth.yml'):
                shared_auth_found = True
                print(f"  ✅ Uses shared authentication workflow in job '{job_name}'")
        
        if not shared_auth_found and len(jobs) > 1:
            print(f"  ℹ️  No shared auth workflow found (may be intentional)")
        
        return True
        
    except Exception as e:
        print(f"❌ {workflow_path.name}: Error - {e}")
        return False

def main():
    """Main validation function."""
    print("🔍 Platform Workflow Validation")
    print("=" * 50)
    
    workflows_dir = Path(__file__).parent.parent / '.github' / 'workflows'
    
    if not workflows_dir.exists():
        print(f"❌ Workflows directory not found: {workflows_dir}")
        return 1
    
    workflow_files = list(workflows_dir.glob('*.yml'))
    
    if not workflow_files:
        print(f"❌ No workflow files found in {workflows_dir}")
        return 1
    
    print(f"Found {len(workflow_files)} workflow files")
    print()
    
    all_valid = True
    for workflow_file in sorted(workflow_files):
        if not validate_workflow_file(workflow_file):
            all_valid = False
        print()
    
    # Check for platform-specific requirements
    print("🎯 Platform-Specific Requirements Check:")
    print("-" * 40)
    
    # Check that core platform logic files exist
    core_files = [
        'app/main.py',  # Platform aggregator
        'app/tagging_service.py',  # Platform tagging service
        'config/services.yaml',  # Service configuration
    ]
    
    for file_path in core_files:
        full_path = Path(__file__).parent.parent / file_path
        if full_path.exists():
            print(f"✅ Core platform file exists: {file_path}")
        else:
            print(f"❌ Missing core platform file: {file_path}")
            all_valid = False
    
    print()
    
    if all_valid:
        print("🎉 All platform workflows validated successfully!")
        print("✅ Phase 2 migration appears successful")
        return 0
    else:
        print("❌ Some validation issues found")
        return 1

if __name__ == '__main__':
    sys.exit(main())
