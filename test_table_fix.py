#!/usr/bin/env python3
"""
Test the table processing fix
"""

import requests
import json
from pathlib import Path

def test_api_table_processing():
    """Test table processing via API"""
    
    # Test configuration
    api_url = "http://localhost:1157/api/pdf/parse-pages"
    pdf_path = str(Path("test_table.pdf").absolute())
    
    print("=== Table Processing Fix Test ===")
    print(f"Testing with: {pdf_path}")
    
    # Test 1: Original mode (should now use TableAwarePageParser)
    print("\n1. Testing enhanced table-aware mode (use_hybrid_mode=false)...")
    
    test_data = {
        "pdf_path": pdf_path,
        "pages": [8],  # Page with table data
        "save_markdown": True,
        "enhanced_table_mode": True,
        "use_hybrid_mode": False  # This should now use TableAwarePageParser
    }
    
    try:
        response = requests.post(api_url, json=test_data, timeout=60)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Success: {result.get('success', False)}")
            print(f"  Processed: {result.get('processed_pages', 0)} pages")
            print(f"  Tokens: {result.get('metering', {}).get('input_tokens', 0)}/{result.get('metering', {}).get('output_tokens', 0)}")
            
            pages = result.get('pages', [])
            if pages:
                page_content = pages[0].get('markdown_content', '')
                print(f"\n📄 Content Preview (first 500 chars):")
                print("="*60)
                print(page_content[:500])
                print("="*60)
                
                # Check for table indicators
                table_indicators = ['|', 'table', '表', '项目', '值']
                found_indicators = [ind for ind in table_indicators if ind in page_content.lower()]
                
                if found_indicators:
                    print(f"✅ Table indicators found: {found_indicators}")
                else:
                    print("⚠️  No table indicators found")
                
                # Check content quality
                if len(page_content.strip()) > 50:
                    print("✅ Content has reasonable length")
                else:
                    print("⚠️  Content seems too short")
                    
                # Check for proper table structure
                if '|' in page_content and page_content.count('|') >= 4:
                    print("✅ Found Markdown table structure")
                elif '<table>' in page_content:
                    print("✅ Found HTML table structure")
                else:
                    print("ℹ️  No clear table structure detected")
            
        else:
            print(f"✗ Request failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"  Error: {error_data.get('error', 'Unknown error')}")
            except:
                print(f"  Raw response: {response.text[:200]}")
    
    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        print("Make sure the API server is running: python api_server.py")
    
    # Test 2: Hybrid mode comparison
    print(f"\n2. Testing hybrid mode (use_hybrid_mode=true)...")
    
    test_data['use_hybrid_mode'] = True
    
    try:
        response = requests.post(api_url, json=test_data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            pages = result.get('pages', [])
            if pages:
                page_content = pages[0].get('markdown_content', '')
                print(f"✓ Hybrid mode content length: {len(page_content)}")
                print(f"  Preview: {page_content[:100]}...")
        else:
            print(f"⚠️  Hybrid mode failed: {response.status_code}")
    
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Hybrid mode test failed: {e}")

if __name__ == "__main__":
    test_api_table_processing()