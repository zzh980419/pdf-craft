# Remote API Usage Guide

This document describes how to use the remote API functionality that has been added to PDF-Craft.

## Overview

The remote API module allows PDF-Craft to use remote OCR services (like DeepSeek-OCR) instead of local models. This includes:

- Remote API client for OCR services
- Page-based PDF parsing functionality 
- RESTful API server for PDF processing

## Configuration

### 1. Environment Variables

Create a `.env` file in the project root with the following configuration:

```bash
# OCR Provider Configuration
OCR_PROVIDER=DEEPSEEK_OCR

# DeepSeek OCR Configuration
DEEPSEEK_OCR_BASE_URL=http://100.64.0.177:19002
DEEPSEEK_OCR_API_KEY=
DEEPSEEK_OCR_MODEL=deepseek-ai/DeepSeek-OCR

# Optional Configuration
OCR_API_TIMEOUT=120
TABLE_RENDER_MODE=html

# Markdown Output Directory
MD_OUTPUT_DIR=outputs
```

### 2. Dependencies

Ensure you have the required dependencies:
- `requests` - for HTTP API calls
- `Pillow` - for image processing
- `Flask` - for the API server

## Usage

### 1. Direct Python API

```python
from pdf_craft.remote_api import load_config, AIAPIClient
from pdf_craft.remote_api.page_parser import transform_pages_markdown

# Parse specific pages and save markdown files
page_results, metering = transform_pages_markdown(
    pdf_path="document.pdf",
    pages=[1, 2, 3],  # Parse pages 1, 2, 3
    markdown_assets_path="output/assets",
    max_ocr_output_tokens=4096,
    save_markdown=True  # Save markdown files to disk
)

print(f"Processed {len(page_results)} pages")
for page_info in page_results:
    page_num = page_info["page_number"]
    content = page_info["markdown_content"]
    file_path = page_info["file_path"]
    
    print(f"Page {page_num}: {content[:100]}...")
    if file_path:
        print(f"  Saved to: {file_path}")
```

### 2. REST API Server

#### Start the Server

```bash
python api_server.py
```

The server will start on `http://localhost:1157`

#### Available Endpoints

##### Health Check
```bash
GET /health
```

Returns service status and API connection test.

##### Configuration Info
```bash
GET /api/config
```

Returns current API configuration.

##### Parse PDF Pages
```bash
POST /api/pdf/parse-pages
```

Request body:
```json
{
    "pdf_path": "/path/to/document.pdf",
    "pages": [1, 2, 3],  // Optional: specific pages to parse
    "save_markdown": true,  // Optional: save markdown files to disk
    "enhanced_table_mode": true  // Optional: enhanced table recognition (default: true)
}
```

Response:
```json
{
    "success": true,
    "pdf_path": "/path/to/document.pdf",
    "total_pages": 10,
    "processed_pages": 3,
    "pages": [
        {
            "page_number": 1,
            "markdown_content": "# Page 1\n\nContent...",
            "file_path": "/absolute/path/to/outputs/document_abc123/document_1.md"
        }
    ],
    "metering": {
        "input_tokens": 1500,
        "output_tokens": 800
    },
    "duration_seconds": 12.5
}
```

### 3. Example Usage with curl

```bash
# Health check
curl -X GET http://localhost:1157/health

# Parse first page of a PDF with enhanced table recognition
curl -X POST http://localhost:1157/api/pdf/parse-pages \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "/path/to/document.pdf",
    "pages": [1],
    "save_markdown": true,
    "enhanced_table_mode": true
  }'
```

## Testing

### 1. Test Core Functionality

```bash
python test_remote_api.py
```

This tests:
- Configuration loading
- API client initialization
- PDF validation
- Basic page parsing (if test PDF available)

### 2. Test API Server

```bash
# Start the API server first
python api_server.py

# In another terminal, test the endpoints
python test_api_server.py [optional_pdf_path]
```

## Architecture

### Module Structure

```
pdf_craft/
└── remote_api/
    ├── __init__.py          # Module exports
    ├── config.py            # Configuration management
    ├── client.py            # Remote API client
    └── page_parser.py       # Page-based parsing functionality
```

### Key Components

1. **APIConfig**: Configuration management for remote API settings
2. **AIAPIClient**: HTTP client for communicating with remote OCR services
3. **PageTransform**: Page-based PDF processing using remote API
4. **transform_pages_markdown()**: Main function for page-based parsing

### Integration with Original Code

The remote API module is designed as an add-on that:
- Does not modify original PDF-Craft code
- Uses the existing PDF handling infrastructure
- Provides the same interface as the original functions
- Can be easily removed without breaking the core system

## Error Handling

The system includes comprehensive error handling for:
- Network connectivity issues
- API rate limits and quotas
- Invalid PDF files or page numbers
- Configuration errors
- OCR processing failures

## Performance Considerations

- Pages are processed individually to allow selective parsing
- Network timeouts are configurable
- Token limits can be set to control API usage
- Assets are saved locally to avoid re-processing

## Troubleshooting

### Common Issues

1. **Configuration Error**: Ensure `.env` file is present and contains valid settings
2. **Network Error**: Check API server connectivity and credentials
3. **PDF Not Found**: Verify PDF file path is absolute and file exists
4. **API Quota**: Monitor token usage and API limits

### Debug Mode

Set `debug=True` in the API configuration to see detailed request/response logs.

## Migration from Project A

This implementation replicates the functionality from your previous project (Project A) but using the new codebase structure. The key differences:

- Uses new project's PDF handling classes
- Simplified error handling
- Direct remote API integration without local model fallback
- Compatible with latest upstream changes

## Future Enhancements

Potential improvements:
- Batch processing for multiple pages
- Caching of processed pages
- Support for additional OCR providers
- Async processing for better performance