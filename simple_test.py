print("Starting test...")

try:
    import sys
    sys.path.insert(0, '.')
    print("Path added")
    
    from pdf_craft.remote_api.config import load_config
    print("Config import: OK")
    
    from pdf_craft.remote_api.client import AIAPIClient
    print("Client import: OK")
    
    from pdf_craft.remote_api.hybrid_parser import HybridPageTransform
    print("Hybrid parser import: OK")
    
    # Test initialization
    config = load_config()
    print("Config loaded:", config.provider)
    
    hybrid = HybridPageTransform()
    print("Hybrid parser initialized")
    print("Has doc-page-extractor:", hybrid._has_doc_page_extractor)
    
except Exception as e:
    import traceback
    print("Error:", e)
    print("Traceback:", traceback.format_exc())

print("Test completed.")