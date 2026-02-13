#!/usr/bin/env python3
"""
Test table recognition with both remote API and hybrid approach
"""

import sys
import json
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_remote_api_only():
    """Test table recognition with pure remote API"""
    print("=== Testing Remote API Only ===")
    
    try:
        from pdf_craft.remote_api.page_parser import transform_pages_markdown
        
        pdf_path = "test_table.pdf"
        if not Path(pdf_path).exists():
            print(f"✗ Test PDF not found: {pdf_path}")
            return False
        
        # Test with page containing tables (page 8 has oil reservoir data table)
        print(f"Processing page 8 (contains oil reservoir data table)...")
        
        page_results, metering = transform_pages_markdown(
            pdf_path=pdf_path,
            pages=[8],  # Page with table
            markdown_assets_path="outputs/remote_api_test_assets",
            use_remote_api=True,
            max_ocr_tokens=4096,
            max_ocr_output_tokens=4096,
            save_markdown=True,
            enhanced_table_mode=True
        )
        
        print(f"✓ Remote API processing completed")
        print(f"  Pages processed: {len(page_results)}")
        print(f"  Input tokens: {metering.input_tokens}")
        print(f"  Output tokens: {metering.output_tokens}")
        
        # Show content preview
        if page_results:
            content = page_results[0]['markdown_content']
            print(f"\nContent preview (first 500 chars):")
            print(content[:500] + ("..." if len(content) > 500 else ""))
            
            # Check for table indicators
            table_indicators = ['|', '表1', '表2', '表3', '表4', 'table']
            found_indicators = [ind for ind in table_indicators if ind in content]
            if found_indicators:
                print(f"✓ Table indicators found: {found_indicators}")
            else:
                print("✗ No table indicators found in content")
        
        return True
        
    except Exception as e:
        print(f"✗ Remote API test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_hybrid_approach():
    """Test table recognition with hybrid approach"""
    print("\n=== Testing Hybrid Approach ===")
    
    try:
        from pdf_craft.remote_api.hybrid_parser import transform_pages_markdown_hybrid
        
        pdf_path = "test_table.pdf"
        if not Path(pdf_path).exists():
            print(f"✗ Test PDF not found: {pdf_path}")
            return False
        
        print(f"Processing page 8 with hybrid approach...")
        
        page_results, metering = transform_pages_markdown_hybrid(
            pdf_path=pdf_path,
            pages=[8],  # Page with table
            markdown_assets_path="outputs/hybrid_test_assets",
            use_remote_api=True,
            max_ocr_tokens=4096,
            max_ocr_output_tokens=4096,
            save_markdown=True,
            enhanced_table_mode=True,
            use_original_ocr_fallback=True
        )
        
        print(f"✓ Hybrid processing completed")
        print(f"  Pages processed: {len(page_results)}")
        print(f"  Input tokens: {metering.input_tokens}")
        print(f"  Output tokens: {metering.output_tokens}")
        
        # Show content preview
        if page_results:
            content = page_results[0]['markdown_content']
            print(f"\nContent preview (first 500 chars):")
            print(content[:500] + ("..." if len(content) > 500 else ""))
            
            # Check for table indicators
            table_indicators = ['|', '表1', '表2', '表3', '表4', 'table']
            found_indicators = [ind for ind in table_indicators if ind in content]
            if found_indicators:
                print(f"✓ Table indicators found: {found_indicators}")
            else:
                print("✗ No table indicators found in content")
        
        return True
        
    except Exception as e:
        print(f"✗ Hybrid approach test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_api_server():
    """Test table recognition via API server"""
    print("\n=== Testing API Server ===")
    
    try:
        import requests
        
        # Test health endpoint
        print("Testing health endpoint...")
        response = requests.get("http://localhost:1157/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✓ API server is healthy")
            print(f"  API status: {health_data.get('api_status', 'unknown')}")
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
        
        # Test parse endpoint with hybrid mode
        print("Testing parse endpoint with hybrid mode...")
        parse_data = {
            "pdf_path": str(Path("test_table.pdf").absolute()),
            "pages": [8],  # Page with table
            "save_markdown": True,
            "enhanced_table_mode": True,
            "use_hybrid_mode": True
        }
        
        response = requests.post(
            "http://localhost:1157/api/pdf/parse-pages", 
            json=parse_data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ API parse completed")
            print(f"  Success: {result.get('success', False)}")
            print(f"  Pages processed: {result.get('processed_pages', 0)}")
            print(f"  Duration: {result.get('duration_seconds', 0)}s")
            
            # Check content
            pages = result.get('pages', [])
            if pages:
                content = pages[0].get('markdown_content', '')
                print(f"\nContent preview (first 300 chars):")
                print(content[:300] + ("..." if len(content) > 300 else ""))
        else:
            print(f"✗ API parse failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"  Error: {error_data.get('error', 'Unknown error')}")
            except:
                print(f"  Raw response: {response.text[:200]}")
            return False
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to API server (not running?)")
        print("  Start the server with: python api_server.py")
        return False
    except Exception as e:
        print(f"✗ API server test failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Table Recognition Test ===")
    print("Testing with PDF containing tables and structured data\n")
    
    # Test 1: Remote API only
    remote_api_ok = test_remote_api_only()
    
    # Test 2: Hybrid approach
    hybrid_ok = test_hybrid_approach()
    
    # Test 3: API server (optional)
    api_server_ok = test_api_server()
    
    # Summary
    print("\n=== Test Summary ===")
    print(f"Remote API: {'✓' if remote_api_ok else '✗'}")
    print(f"Hybrid approach: {'✓' if hybrid_ok else '✗'}")
    print(f"API server: {'✓' if api_server_ok else '✗'}")
    
    if remote_api_ok or hybrid_ok:
        print("\n✓ Table recognition functionality is working!")
        if hybrid_ok and remote_api_ok:
            print("  Both remote API and hybrid modes are available.")
        elif hybrid_ok:
            print("  Hybrid mode with original OCR integration is available.")
        elif remote_api_ok:
            print("  Remote API mode is available.")
    else:
        print("\n✗ Table recognition needs troubleshooting.")
    
    print("\nCheck the outputs/ directory for generated markdown files.")