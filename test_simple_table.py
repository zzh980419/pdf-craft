import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, '.')

# Set environment variables
os.environ.setdefault('OCR_PROVIDER', 'DEEPSEEK_OCR')
os.environ.setdefault('DEEPSEEK_OCR_BASE_URL', 'http://100.64.0.177:19002')
os.environ.setdefault('MD_OUTPUT_DIR', 'outputs')

print("=== Simple Table Recognition Test ===")

try:
    print("1. Testing imports...")
    from pdf_craft.remote_api.hybrid_parser import transform_pages_markdown_hybrid
    print("✓ Hybrid parser imported")
    
    from pdf_craft.remote_api.page_parser import transform_pages_markdown
    print("✓ Page parser imported")
    
    pdf_path = "test_table.pdf"
    if not Path(pdf_path).exists():
        print(f"✗ PDF not found: {pdf_path}")
        sys.exit(1)
    
    print(f"✓ PDF found: {pdf_path}")
    
    print("\n2. Testing remote API mode...")
    try:
        page_results, metering = transform_pages_markdown(
            pdf_path=pdf_path,
            pages=[8],
            markdown_assets_path="outputs/test_assets",
            use_remote_api=True,
            max_ocr_tokens=4096,
            max_ocr_output_tokens=4096,
            save_markdown=True,
            enhanced_table_mode=True
        )
        
        print(f"✓ Remote API completed")
        print(f"  Pages: {len(page_results)}")
        print(f"  Tokens: {metering.input_tokens}/{metering.output_tokens}")
        
        if page_results:
            content = page_results[0]['markdown_content'][:200]
            print(f"  Preview: {content}...")
    except Exception as e:
        print(f"✗ Remote API failed: {e}")
    
    print("\n3. Testing hybrid mode...")
    try:
        page_results, metering = transform_pages_markdown_hybrid(
            pdf_path=pdf_path,
            pages=[8],
            markdown_assets_path="outputs/hybrid_assets",
            use_remote_api=True,
            max_ocr_tokens=4096,
            max_ocr_output_tokens=4096,
            save_markdown=True,
            enhanced_table_mode=True,
            use_original_ocr_fallback=True
        )
        
        print(f"✓ Hybrid mode completed")
        print(f"  Pages: {len(page_results)}")
        print(f"  Tokens: {metering.input_tokens}/{metering.output_tokens}")
        
        if page_results:
            content = page_results[0]['markdown_content'][:200]
            print(f"  Preview: {content}...")
    except Exception as e:
        print(f"✗ Hybrid mode failed: {e}")
    
    print("\n✓ Test completed successfully!")
    
except Exception as e:
    print(f"✗ Test failed: {e}")
    import traceback
    traceback.print_exc()