#!/usr/bin/env python3
"""
Test the simplified prompt fix
"""

import requests
import json
from pathlib import Path
import time

def test_prompt_fix():
    """Test the simplified prompt fix"""
    
    print("=== Testing Simplified Prompt Fix ===")
    
    # Wait a moment for server restart
    print("Waiting for server to restart...")
    time.sleep(3)
    
    # Test single page with table content
    test_data = {
        "pdf_path": str(Path("test_table.pdf").absolute()),
        "pages": [8],  # Page known to have table content
        "save_markdown": True,
        "enhanced_table_mode": True,
        "use_hybrid_mode": False  # Using our fixed TableAwarePageParser
    }
    
    api_url = "http://localhost:1157/api/pdf/parse-pages"
    
    try:
        print(f"Testing page 8 (table content) with simplified prompt...")
        response = requests.post(api_url, json=test_data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Status: Success")
            print(f"  Tokens: {result.get('metering', {}).get('input_tokens', 0)}/{result.get('metering', {}).get('output_tokens', 0)}")
            
            pages = result.get('pages', [])
            if pages:
                page = pages[0]
                content = page.get('markdown_content', '')
                
                print(f"\n📄 Content Analysis:")
                print(f"  Length: {len(content)} characters")
                print(f"  Lines: {len(content.splitlines())}")
                
                if len(content.strip()) > 50:
                    print(f"✅ Content has reasonable length")
                    
                    print(f"\n📝 Content Preview:")
                    print("="*60)
                    print(content[:800])
                    if len(content) > 800:
                        print("... [truncated]")
                    print("="*60)
                    
                    # Check for improvements
                    if any(indicator in content.lower() for indicator in ['table', '表', '|', ':']):
                        print("✅ Found table/structured content indicators")
                    else:
                        print("ℹ️  No obvious table indicators")
                        
                else:
                    print("⚠️  Content is still too short")
                    print(f"Full content: '{content}'")
        else:
            print(f"✗ Request failed: {response.status_code}")
            print(f"Response: {response.text}")
    
    except Exception as e:
        print(f"✗ Test failed: {e}")

    # Test another page for comparison
    print(f"\n" + "="*60)
    print("Testing page 5 for comparison...")
    
    test_data['pages'] = [5]
    
    try:
        response = requests.post(api_url, json=test_data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            pages = result.get('pages', [])
            if pages:
                content = pages[0].get('markdown_content', '')
                print(f"Page 5 content length: {len(content)}")
                if len(content) > 50:
                    print("Preview:", content[:200])
        
    except Exception as e:
        print(f"Page 5 test failed: {e}")

if __name__ == "__main__":
    test_prompt_fix()