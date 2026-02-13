#!/usr/bin/env python3
"""
Test the simple remote API replacement
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, '.')

print("=== Simple Remote API Test ===")

try:
    # Test 1: Simple transform function (recommended approach)
    print("1. Testing simple transform function...")
    from pdf_craft.remote_api import transform_pdf_to_markdown_remote
    
    pdf_path = "test_table.pdf"
    output_dir = "outputs/simple_remote_test"
    
    if not Path(pdf_path).exists():
        print(f"✗ PDF not found: {pdf_path}")
        sys.exit(1)
    
    print(f"Processing PDF: {pdf_path}")
    print(f"Output directory: {output_dir}")
    
    # Process specific pages (e.g., page 8 which has tables)
    metering = transform_pdf_to_markdown_remote(
        pdf_path=pdf_path,
        output_dir=output_dir,
        pages=[1, 8],  # Test with cover page and a table page
    )
    
    print(f"✓ Transform completed!")
    print(f"  Input tokens: {metering.input_tokens}")
    print(f"  Output tokens: {metering.output_tokens}")
    
    # Check output files
    output_path = Path(output_dir)
    markdown_files = list((output_path / "markdown").glob("*.md"))
    asset_files = list((output_path / "assets").glob("*"))
    
    print(f"  Generated files:")
    print(f"    Markdown files: {len(markdown_files)}")
    print(f"    Asset files: {len(asset_files)}")
    
    for md_file in markdown_files:
        print(f"    - {md_file.name}")
        # Show a preview
        content = md_file.read_text(encoding='utf-8')
        print(f"      Preview: {content[:100].replace(chr(10), ' ')}...")
    
    print("\n" + "="*50)
    print("SUCCESS: Simple remote API replacement is working!")
    print("="*50)
    
    print("\nTo use this in your code, simply replace:")
    print("  from pdf_craft.pdf import OCR")
    print("with:")
    print("  from pdf_craft.remote_api import RemoteOCR as OCR")
    print("\nOr use the simple transform function:")
    print("  from pdf_craft.remote_api import transform_pdf_to_markdown_remote")
    
    
except Exception as e:
    print(f"✗ Test failed: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nTroubleshooting tips:")
    print("1. Check your .env configuration")
    print("2. Ensure the remote API is accessible")
    print("3. Verify the PDF file exists")