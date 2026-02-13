#!/usr/bin/env python3
"""
Debug the table parser to see what's happening
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, '.')

def debug_single_page():
    """Debug processing of a single page"""
    
    print("=== TableAwarePageParser Debug ===")
    
    try:
        from pdf_craft.remote_api.table_aware_parser import TableAwarePageParser
        
        pdf_path = "test_table.pdf"
        page_num = 8  # Page with table data
        
        if not Path(pdf_path).exists():
            print(f"✗ PDF not found: {pdf_path}")
            return
        
        print(f"Testing page {page_num} of {pdf_path}")
        
        # Create parser with debug mode
        parser = TableAwarePageParser()
        
        # Enable debug in API client
        parser._api_client.config.debug = True
        
        print("\n1. Processing page...")
        markdown_content, metering = parser.process_page(
            pdf_path=pdf_path,
            page_num=page_num,
            enhanced_table_mode=True
        )
        
        print(f"\n2. Results:")
        print(f"   Tokens: {metering.input_tokens}/{metering.output_tokens}")
        print(f"   Content length: {len(markdown_content)}")
        
        print(f"\n3. Content:")
        print("="*60)
        print(markdown_content[:1000])
        print("="*60)
        
        if len(markdown_content.strip()) <= 20:  # Only has page header
            print("\n⚠️  Content is mostly empty!")
            
            # Let's debug the API call directly
            print("\n4. Debug API call directly...")
            test_api_directly(pdf_path, page_num)
        
    except Exception as e:
        print(f"✗ Debug failed: {e}")
        import traceback
        traceback.print_exc()

def test_api_directly(pdf_path, page_num):
    """Test API call directly to see raw response"""
    
    try:
        from pdf_craft.remote_api.config import load_config
        from pdf_craft.remote_api.client import AIAPIClient
        from pdf_craft.pdf.handler import DefaultPDFHandler
        from PIL import Image
        
        print("   Loading config...")
        config = load_config()
        config.debug = True  # Force debug mode
        
        print(f"   Config: {config.provider}, {config.base_url}, {config.default_model}")
        
        client = AIAPIClient(config)
        handler = DefaultPDFHandler()
        
        print("   Rendering page...")
        doc = handler.open(Path(pdf_path))
        try:
            page_image = doc.render_page(page_num, dpi=200)
            print(f"   Image size: {page_image.size}, mode: {page_image.mode}")
        finally:
            doc.close()
        
        print("   Calling API...")
        response = client.recognize_image(
            image=page_image,
            max_tokens=4096,
            enhanced_table_mode=True
        )
        
        print(f"   Response keys: {list(response.keys())}")
        
        content = client.extract_text_content(response)
        usage = client.get_usage_info(response)
        
        print(f"   Raw content length: {len(content)}")
        print(f"   Usage: {usage}")
        
        print(f"   Raw content preview:")
        print("-"*40)
        print(repr(content[:200]))
        print("-"*40)
        
        if not content or len(content.strip()) < 10:
            print("   ⚠️  API returned empty or very short content!")
            print("   Full response:")
            print(response)
    
    except Exception as e:
        print(f"   ✗ Direct API test failed: {e}")
        import traceback
        traceback.print_exc()

def test_with_simple_image():
    """Test with a simple text image to verify API works"""
    
    print("\n=== Simple Image Test ===")
    
    try:
        from pdf_craft.remote_api.config import load_config
        from pdf_craft.remote_api.client import AIAPIClient
        from PIL import Image, ImageDraw, ImageFont
        
        config = load_config()
        config.debug = True
        client = AIAPIClient(config)
        
        # Create simple test image
        img = Image.new('RGB', (400, 300), 'white')
        draw = ImageDraw.Draw(img)
        
        # Draw some table-like content
        draw.text((10, 10), "Simple Test Table", fill='black')
        draw.text((10, 40), "Name: John Doe", fill='black')
        draw.text((10, 70), "Age: 30", fill='black')
        draw.text((10, 100), "City: Beijing", fill='black')
        
        # Draw table structure
        draw.rectangle([10, 130, 350, 250], outline='black')
        draw.line([10, 160, 350, 160], fill='black')
        draw.line([150, 130, 150, 250], fill='black')
        
        draw.text((15, 135), "Item", fill='black')
        draw.text((160, 135), "Value", fill='black')
        draw.text((15, 170), "Product A", fill='black')
        draw.text((160, 170), "100", fill='black')
        draw.text((15, 200), "Product B", fill='black')
        draw.text((160, 200), "200", fill='black')
        
        print("Testing simple image...")
        response = client.recognize_image(
            image=img,
            max_tokens=1000,
            enhanced_table_mode=True
        )
        
        content = client.extract_text_content(response)
        usage = client.get_usage_info(response)
        
        print(f"Simple test results:")
        print(f"  Content: '{content}'")
        print(f"  Length: {len(content)}")
        print(f"  Usage: {usage}")
        
        if content and len(content) > 10:
            print("✅ API is working with simple images")
        else:
            print("⚠️  API has issues even with simple images")
        
    except Exception as e:
        print(f"✗ Simple image test failed: {e}")

if __name__ == "__main__":
    debug_single_page()
    test_with_simple_image()