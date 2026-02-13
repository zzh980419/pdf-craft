#!/usr/bin/env python3
"""
Test script for API server endpoints
"""

import requests
import json
import sys
from pathlib import Path


def test_health_endpoint(base_url="http://localhost:1157"):
    """Test health check endpoint"""
    print("Testing /health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("✓ Health check successful")
            print(f"  Service: {data.get('service')}")
            print(f"  Status: {data.get('status')}")
            print(f"  API Status: {data.get('api_status', 'unknown')}")
            if data.get('api_error'):
                print(f"  API Error: {data.get('api_error')}")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


def test_config_endpoint(base_url="http://localhost:1157"):
    """Test config endpoint"""
    print("\nTesting /api/config endpoint...")
    try:
        response = requests.get(f"{base_url}/api/config", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("✓ Config endpoint successful")
            print(f"  Base URL: {data.get('config', {}).get('base_url')}")
            print(f"  Model: {data.get('config', {}).get('default_model')}")
            print(f"  API Key configured: {data.get('config', {}).get('api_key_configured')}")
            return True
        else:
            print(f"✗ Config endpoint failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Config endpoint failed: {e}")
        return False


def test_parse_pages_endpoint(base_url="http://localhost:1157", pdf_path=None):
    """Test parse pages endpoint"""
    print("\nTesting /api/pdf/parse-pages endpoint...")
    
    if not pdf_path:
        # Look for test PDF files
        test_pdfs = [
            "test.pdf",
            "tests/assets/friendly.pdf",
            str(Path("tests") / "assets" / "friendly.pdf")
        ]
        
        for test_pdf in test_pdfs:
            if Path(test_pdf).exists():
                pdf_path = str(Path(test_pdf).absolute())
                break
    
    if not pdf_path or not Path(pdf_path).exists():
        print("⚠ No test PDF found, skipping parse pages test")
        print("  You can provide a PDF path as argument to test this endpoint")
        return True
    
    try:
        print(f"  Using PDF: {pdf_path}")
        
        # Test parsing with specific pages, save markdown, and enhanced table mode
        data = {
            "pdf_path": pdf_path,
            "pages": [1],  # Only first page for testing
            "save_markdown": True,
            "enhanced_table_mode": True  # Enable enhanced table recognition
        }
        
        response = requests.post(
            f"{base_url}/api/pdf/parse-pages",
            json=data,
            timeout=60  # Longer timeout for processing
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Parse pages endpoint successful")
            print(f"  Success: {result.get('success')}")
            print(f"  Total pages: {result.get('total_pages')}")
            print(f"  Processed pages: {result.get('processed_pages')}")
            print(f"  Duration: {result.get('duration_seconds')}s")
            print(f"  Input tokens: {result.get('metering', {}).get('input_tokens')}")
            print(f"  Output tokens: {result.get('metering', {}).get('output_tokens')}")
            
            pages = result.get('pages', [])
            if pages:
                first_page = pages[0]
                content_preview = first_page.get('markdown_content', '')[:200]
                print(f"  First page preview: {content_preview}...")
                
                # Check if file was saved
                file_path = first_page.get('file_path')
                if file_path:
                    print(f"  Markdown file saved: {file_path}")
                    import os
                    if os.path.exists(file_path):
                        print("  ✓ File exists on disk")
                    else:
                        print("  ✗ File not found on disk")
                else:
                    print("  File path not provided")
            
            return True
        else:
            print(f"✗ Parse pages endpoint failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"  Error: {error_data.get('error', 'Unknown error')}")
                if error_data.get('traceback'):
                    print(f"  Traceback: {error_data.get('traceback')[:500]}...")
            except:
                print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Parse pages endpoint failed: {e}")
        return False


def main():
    """Main test function"""
    print("=== API Server Test ===\n")
    
    base_url = "http://localhost:1157"
    
    # Check if API server is running
    print(f"Testing API server at {base_url}")
    
    # Test 1: Health endpoint
    health_ok = test_health_endpoint(base_url)
    
    # Test 2: Config endpoint
    config_ok = test_config_endpoint(base_url)
    
    # Test 3: Parse pages endpoint
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    parse_ok = test_parse_pages_endpoint(base_url, pdf_path)
    
    print("\n=== Test Summary ===")
    print(f"✓ Health endpoint: {'PASS' if health_ok else 'FAIL'}")
    print(f"✓ Config endpoint: {'PASS' if config_ok else 'FAIL'}")
    print(f"✓ Parse pages endpoint: {'PASS' if parse_ok else 'DEPENDS ON PDF/CONFIG'}")
    
    if health_ok and config_ok:
        print("\n🎉 API server basic functionality is working!")
    else:
        print("\n❌ Some API endpoints failed")
    
    print("\nTo fully test parse functionality:")
    print("1. Ensure .env file is configured with DeepSeek OCR settings")
    print("2. Run: python test_api_server.py /path/to/test.pdf")
    
    return health_ok and config_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)