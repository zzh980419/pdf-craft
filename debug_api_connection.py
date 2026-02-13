#!/usr/bin/env python3
"""
Debug API connection and response
"""

import sys
import os
from pathlib import Path
from PIL import Image
import json

# Add current directory to path
sys.path.insert(0, '.')

# Enable debug mode
os.environ['OCR_DEBUG'] = 'true'

print("=== API Connection Debug ===")

try:
    # Test configuration loading
    print("1. Testing configuration...")
    from pdf_craft.remote_api.config import load_config
    config = load_config()
    print(f"✓ Config loaded")
    print(f"  Provider: {config.provider}")
    print(f"  Base URL: {config.base_url}")
    print(f"  Model: {config.default_model}")
    print(f"  Debug mode: {config.debug}")
    print(f"  API key configured: {bool(config.api_key)}")
    
    # Test API client
    print("\n2. Testing API client...")
    from pdf_craft.remote_api.client import AIAPIClient
    client = AIAPIClient(config)
    print("✓ API client created")
    
    # Test with a simple text image
    print("\n3. Creating test image...")
    # Create a simple test image with text
    test_image = Image.new('RGB', (400, 200), 'white')
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(test_image)
    
    # Draw some test text and a simple table
    try:
        # Try to use a default font
        font = ImageFont.load_default()
    except:
        font = None
    
    draw.text((10, 10), "Test Document", fill='black', font=font)
    draw.text((10, 40), "Name: John Doe", fill='black', font=font)
    draw.text((10, 70), "Age: 30", fill='black', font=font)
    draw.text((10, 100), "City: Beijing", fill='black', font=font)
    
    # Draw table lines
    draw.rectangle([10, 130, 350, 180], outline='black')
    draw.line([10, 150, 350, 150], fill='black')
    draw.line([100, 130, 100, 180], fill='black')
    draw.text((15, 135), "Item", fill='black', font=font)
    draw.text((105, 135), "Value", fill='black', font=font)
    draw.text((15, 155), "Product", fill='black', font=font)
    draw.text((105, 155), "100", fill='black', font=font)
    
    print("✓ Test image created")
    
    # Test API call
    print("\n4. Testing API call...")
    response = client.recognize_image(
        image=test_image,
        max_tokens=2048,
        enhanced_table_mode=True
    )
    
    print("✓ API call completed")
    print(f"Response keys: {list(response.keys())}")
    
    # Extract content
    content = client.extract_text_content(response)
    usage = client.get_usage_info(response)
    
    print(f"\n5. Results:")
    print(f"Content length: {len(content)}")
    print(f"Input tokens: {usage['input_tokens']}")
    print(f"Output tokens: {usage['output_tokens']}")
    print(f"Content preview:")
    print("=" * 50)
    print(content[:500] if content else "(empty content)")
    print("=" * 50)
    
    if not content:
        print("\n⚠️  WARNING: Empty content returned!")
        print("Full API response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        print("\n✓ API is working correctly!")
        
    # Test with PDF page
    print("\n6. Testing with PDF page...")
    from pdf_craft.pdf import DefaultPDFHandler
    
    pdf_path = Path("test_table.pdf")
    if pdf_path.exists():
        handler = DefaultPDFHandler()
        doc = handler.open(pdf_path)
        try:
            page_image = doc.render_page(1, dpi=200)
            if isinstance(page_image, Image.Image):
                print("✓ PDF page rendered successfully")
                print(f"  Page size: {page_image.size}")
                print(f"  Page mode: {page_image.mode}")
                
                # Test API with PDF page
                response = client.recognize_image(
                    image=page_image,
                    max_tokens=2048,
                    enhanced_table_mode=True
                )
                
                content = client.extract_text_content(response)
                usage = client.get_usage_info(response)
                
                print(f"  Content length: {len(content)}")
                print(f"  Tokens: {usage['input_tokens']}/{usage['output_tokens']}")
                
                if content:
                    print(f"  Content preview: {content[:200]}...")
                else:
                    print("  ⚠️  Empty content from PDF page!")
            else:
                print("✗ Failed to render PDF page")
        finally:
            doc.close()
    else:
        print("✗ test_table.pdf not found, skipping PDF test")

except Exception as e:
    print(f"✗ Debug failed: {e}")
    import traceback
    traceback.print_exc()

print("\nDebug completed.")