#!/usr/bin/env python3
"""
Test script for hybrid parser functionality
"""

import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test if all required modules can be imported"""
    print("Testing imports...")
    
    try:
        import doc_page_extractor
        print("✓ doc_page_extractor is available")
        doc_page_available = True
    except ImportError as e:
        print("✗ doc_page_extractor import failed:", e)
        doc_page_available = False

    try:
        from pdf_craft.remote_api.hybrid_parser import HybridPageTransform
        print("✓ HybridPageTransform imported successfully")
        hybrid_available = True
    except Exception as e:
        print("✗ HybridPageTransform import failed:", e)
        hybrid_available = False

    try:
        from pdf_craft.remote_api import load_config, AIAPIClient
        print("✓ Remote API components imported successfully")
        api_available = True
    except Exception as e:
        print("✗ Remote API import failed:", e)
        api_available = False
        
    return doc_page_available, hybrid_available, api_available

def test_hybrid_parser():
    """Test hybrid parser initialization"""
    print("\nTesting hybrid parser initialization...")
    
    try:
        from pdf_craft.remote_api.hybrid_parser import HybridPageTransform
        
        # Test initialization without original OCR
        hybrid_transform = HybridPageTransform(
            models_cache_path=None,
            pdf_handler=None,
            local_only=False,
            api_client=None,
            use_original_ocr=False
        )
        print("✓ HybridPageTransform initialized without original OCR")
        
        # Test initialization with original OCR
        hybrid_transform_ocr = HybridPageTransform(
            models_cache_path=None,
            pdf_handler=None,
            local_only=False,
            api_client=None,
            use_original_ocr=True
        )
        print("✓ HybridPageTransform initialized with original OCR")
        
        # Check initialization status
        print(f"  - Has doc-page-extractor: {hybrid_transform._has_doc_page_extractor}")
        print(f"  - Has page extractor node: {hybrid_transform._page_extractor_node is not None}")
        print(f"  - Has original OCR: {hybrid_transform._original_ocr is not None}")
        
        return True
        
    except Exception as e:
        print("✗ HybridPageTransform initialization failed:", e)
        import traceback
        print(traceback.format_exc())
        return False

def test_config_loading():
    """Test configuration loading"""
    print("\nTesting configuration loading...")
    
    try:
        from pdf_craft.remote_api import load_config
        config = load_config()
        print("✓ Configuration loaded successfully")
        print(f"  - Provider: {config.provider}")
        print(f"  - Base URL: {config.base_url}")
        print(f"  - Default model: {config.default_model}")
        print(f"  - API key configured: {bool(config.api_key)}")
        return True
    except Exception as e:
        print("✗ Configuration loading failed:", e)
        return False

if __name__ == "__main__":
    print("=== Hybrid Parser Test ===")
    
    # Test imports
    doc_page_available, hybrid_available, api_available = test_imports()
    
    if not api_available:
        print("Cannot proceed without basic API components")
        sys.exit(1)
    
    # Test configuration
    config_ok = test_config_loading()
    
    # Test hybrid parser
    if hybrid_available:
        hybrid_ok = test_hybrid_parser()
    else:
        hybrid_ok = False
    
    # Summary
    print("\n=== Test Summary ===")
    print(f"doc-page-extractor: {'✓' if doc_page_available else '✗'}")
    print(f"Configuration: {'✓' if config_ok else '✗'}")
    print(f"HybridPageTransform: {'✓' if hybrid_ok else '✗'}")
    
    if hybrid_ok:
        print("\n✓ Hybrid parser is ready for use!")
        if doc_page_available:
            print("  Both original OCR and remote API modes are available.")
        else:
            print("  Remote API mode is available (original OCR requires doc-page-extractor).")
    else:
        print("\n✗ Hybrid parser has issues that need to be resolved.")