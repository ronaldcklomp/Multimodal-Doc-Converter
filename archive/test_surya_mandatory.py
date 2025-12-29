#!/usr/bin/env python3
"""Test that Surya is now a mandatory dependency."""

import sys
import subprocess
import importlib.util

def test_surya_import():
    """Test that Surya can be imported."""
    print("Testing Surya import...")
    try:
        # Try to import Surya modules
        from surya.foundation import FoundationPredictor
        from surya.layout import LayoutPredictor
        from surya.settings import settings
        print("✓ Surya imports work")
        return True
    except ImportError as e:
        print(f"✗ Surya import failed: {e}")
        return False

def test_layout_analysis_import():
    """Test that layout_analysis module imports correctly."""
    print("\nTesting layout_analysis import...")
    try:
        # Add src to path
        sys.path.insert(0, 'src')
        from mmrag_converter.layout_analysis import extract_layout_aware_text, _get_surya_predictor
        print("✓ layout_analysis imports work")
        
        # Check that _get_surya_predictor doesn't raise ModuleNotFoundError
        try:
            predictor = _get_surya_predictor()
            print("✓ _get_surya_predictor works")
        except ModuleNotFoundError as e:
            print(f"✗ _get_surya_predictor failed: {e}")
            return False
            
        return True
    except ImportError as e:
        print(f"✗ layout_analysis import failed: {e}")
        return False

def test_dependencies():
    """Check that dependencies are correctly listed."""
    print("\nChecking dependencies...")
    
    # Read pyproject.toml
    with open('pyproject.toml', 'r') as f:
        content = f.read()
        if 'surya-ocr==0.17.0' in content:
            print("✓ surya-ocr==0.17.0 found in pyproject.toml")
        else:
            print("✗ surya-ocr==0.17.0 NOT found in pyproject.toml")
            
    # Read setup.py
    with open('setup.py', 'r') as f:
        content = f.read()
        if 'surya-ocr==0.17.0' in content:
            print("✓ surya-ocr==0.17.0 found in setup.py")
        else:
            print("✗ surya-ocr==0.17.0 NOT found in setup.py")

def main():
    print("=== Testing Surya as Mandatory Dependency ===\n")
    
    all_passed = True
    
    # Test 1: Check dependencies
    test_dependencies()
    
    # Test 2: Try to import Surya
    if not test_surya_import():
        all_passed = False
        print("\nNote: Surya may not be installed yet.")
        print("Install it with: pip install surya-ocr")
    
    # Test 3: Test layout_analysis module
    if not test_layout_analysis_import():
        all_passed = False
    
    print("\n" + "="*50)
    if all_passed:
        print("✓ All tests passed! Surya is now mandatory.")
        print("\nTo install the package with Surya:")
        print("  pip install -e .")
    else:
        print("⚠️ Some tests failed.")
        print("\nMake sure to:")
        print("1. Install Surya: pip install surya-ocr")
        print("2. Reinstall package: pip install -e .")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
