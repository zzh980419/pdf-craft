#!/usr/bin/env python3
"""
Check API response format and content
"""

import sys
import os
import json
import requests
from pathlib import Path

# Add current directory to path
sys.path.insert(0, '.')

# Enable debug mode
os.environ['OCR_DEBUG'] = 'true'

print("=== API Response Format Check ===")

try:
    from pdf_craft.remote_api.config import load_config
    config = load_config()
    
    print(f"Config loaded:")
    print(f"  Base URL: {config.base_url}")
    print(f"  Model: {config.default_model}")
    print(f"  Debug: {config.debug}")
    
    # Test direct API call
    print(f"\n1. Testing direct API call...")
    
    url = f"{config.base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    # Add API key if available
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    
    # Simple text request first
    simple_request = {
        "model": config.default_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请回复 'Hello, this is a test response.'"
                    }
                ]
            }
        ],
        "stream": False,
        "max_tokens": 100
    }
    
    print(f"Calling API: {url}")
    print(f"Headers: {headers}")
    print(f"Request: {json.dumps(simple_request, indent=2, ensure_ascii=False)}")
    
    response = requests.post(url, headers=headers, json=simple_request, timeout=30)
    
    print(f"\nResponse status: {response.status_code}")
    print(f"Response headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        response_data = response.json()
        print(f"\nResponse data structure:")
        print(f"Keys: {list(response_data.keys())}")
        
        if 'choices' in response_data:
            print(f"Choices: {len(response_data['choices'])}")
            if response_data['choices']:
                choice = response_data['choices'][0]
                print(f"First choice keys: {list(choice.keys())}")
                
                if 'message' in choice:
                    message = choice['message']
                    print(f"Message keys: {list(message.keys())}")
                    content = message.get('content', '')
                    print(f"Content: '{content}'")
                    print(f"Content length: {len(content)}")
        
        if 'usage' in response_data:
            usage = response_data['usage']
            print(f"Usage: {usage}")
        
        print(f"\nFull response:")
        print("=" * 60)
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        print("=" * 60)
    else:
        print(f"API call failed: {response.status_code}")
        print(f"Error response: {response.text}")
    
    # Test with image if simple call works
    if response.status_code == 200:
        print(f"\n2. Testing with image...")
        
        from pdf_craft.remote_api.client import AIAPIClient
        from PIL import Image, ImageDraw, ImageFont
        
        client = AIAPIClient(config)
        
        # Create test image
        test_image = Image.new('RGB', (300, 100), 'white')
        draw = ImageDraw.Draw(test_image)
        draw.text((10, 10), "Test Table:", fill='black')
        draw.text((10, 30), "Name | Age", fill='black')
        draw.text((10, 50), "John | 25", fill='black')
        draw.text((10, 70), "Jane | 30", fill='black')
        
        print("Testing image recognition...")
        
        try:
            image_response = client.recognize_image(
                image=test_image,
                max_tokens=1000,
                enhanced_table_mode=True
            )
            
            content = client.extract_text_content(image_response)
            usage = client.get_usage_info(image_response)
            
            print(f"Image OCR result:")
            print(f"  Content: '{content}'")
            print(f"  Length: {len(content)}")
            print(f"  Usage: {usage}")
            
        except Exception as e:
            print(f"Image OCR failed: {e}")
            import traceback
            traceback.print_exc()

except Exception as e:
    print(f"Test failed: {e}")
    import traceback
    traceback.print_exc()