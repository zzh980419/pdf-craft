"""
Flask API server for PDF-Craft with remote API support

Provides RESTful API endpoints for page-based PDF parsing
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from flask import Flask, request, jsonify

from pdf_craft.remote_api import load_config, AIAPIClient
from pdf_craft.remote_api.page_parser import transform_pages_markdown, validate_pdf_path
from pdf_craft.remote_api.hybrid_parser import transform_pages_markdown_hybrid
from pdf_craft.pdf import DefaultPDFHandler

app = Flask(__name__)
app.config['OUTPUT_FOLDER'] = 'outputs'

# Ensure output folder exists
Path(app.config['OUTPUT_FOLDER']).absolute().mkdir(parents=True, exist_ok=True)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with remote AI API connection test"""
    start_time = time.time()
    
    try:
        # Basic health status
        result = {
            'status': 'healthy',
            'service': 'pdf-craft-api',
            'version': '1.0.0',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        # Test remote AI API connection
        try:
            config = load_config()
            client = AIAPIClient(config)
            
            # Send simple test request
            test_response = client.recognize_text(
                images=["Connection test"],  # Simple test text
                prompt="Please reply 'Connection successful'",
                model=config.default_model
            )
            
            result.update({
                'api_status': 'connected',
                'api_test': 'success',
                'api_response': test_response[:100] if test_response else 'Empty response',
                'api_model': config.default_model,
                'api_base_url': config.base_url
            })
            
        except Exception as api_error:
            result.update({
                'api_status': 'disconnected',
                'api_test': 'failed',
                'api_error': str(api_error)[:200],  # Limit error message length
                'api_base_url': getattr(load_config(), 'base_url', 'Unknown')
            })
        
        # Calculate response time
        duration_seconds = round(time.time() - start_time, 3)
        result['duration_seconds'] = duration_seconds
        
        return jsonify(result)
    
    except Exception as e:
        duration_seconds = round(time.time() - start_time, 3)
        return jsonify({
            'status': 'error',
            'service': 'pdf-craft-api',
            'error': str(e),
            'duration_seconds': duration_seconds
        }), 500


@app.route('/api/pdf/parse-pages', methods=['POST'])
def parse_pdf_pages():
    """
    Page-based PDF parsing API
    
    Accepts PDF file path and optional page numbers array,
    returns parsed Markdown content by page
    """
    start_time = time.time()
    
    try:
        # Get request data (supports both JSON and form formats)
        if request.is_json:
            data = request.get_json()
        elif request.form:
            data = request.form.to_dict()
            # Handle arrays in form data
            if 'pages' in data:
                try:
                    data['pages'] = json.loads(data['pages'])
                except (json.JSONDecodeError, TypeError):
                    data['pages'] = []
        else:
            return jsonify({'error': 'Request must contain JSON data or form data'}), 400
        
        if not data:
            return jsonify({'error': 'Request data is empty'}), 400
        
        # Get PDF path
        pdf_path = data.get('pdf_path')
        if not pdf_path:
            return jsonify({'error': 'pdf_path is required'}), 400
        
        # Validate PDF path
        is_valid, error_msg = validate_pdf_path(pdf_path)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Get page numbers array parameter
        pages = data.get('pages', [])
        if not isinstance(pages, list):
            return jsonify({'error': 'pages must be an array'}), 400
        
        # Get save_markdown parameter
        save_markdown = data.get('save_markdown', False)
        if not isinstance(save_markdown, bool):
            return jsonify({'error': 'save_markdown must be a boolean'}), 400
        
        # Get enhanced_table_mode parameter
        enhanced_table_mode = data.get('enhanced_table_mode', True)
        if not isinstance(enhanced_table_mode, bool):
            return jsonify({'error': 'enhanced_table_mode must be a boolean'}), 400
        
        # Get use_hybrid_mode parameter
        use_hybrid_mode = data.get('use_hybrid_mode', False)
        if not isinstance(use_hybrid_mode, bool):
            return jsonify({'error': 'use_hybrid_mode must be a boolean'}), 400
        
        # Set output path
        output_name = Path(pdf_path).stem
        assets_path = Path(app.config['OUTPUT_FOLDER']).absolute() / f"{output_name}_assets"
        
        # Get PDF total pages
        handler = DefaultPDFHandler()
        document = handler.open(Path(pdf_path))
        try:
            total_pdf_pages = document.pages_count
        finally:
            document.close()
        
        # Handle page logic
        if pages:
            # Filter valid page numbers
            valid_pages = []
            invalid_pages = []
            
            for page_num in pages:
                try:
                    page_num = int(page_num)
                    if 1 <= page_num <= total_pdf_pages:
                        valid_pages.append(page_num)
                    else:
                        invalid_pages.append(page_num)
                except (ValueError, TypeError):
                    invalid_pages.append(page_num)
            
            if not valid_pages:
                return jsonify({
                    'error': f'No valid pages specified. PDF has {total_pdf_pages} pages.',
                    'invalid_pages': invalid_pages
                }), 400
            
            # Choose processing method based on mode
            if use_hybrid_mode:
                # Use hybrid mode (original structure detection + remote API)
                page_results, metering = transform_pages_markdown_hybrid(
                    pdf_path=pdf_path,
                    pages=valid_pages,
                    markdown_assets_path=assets_path,
                    use_remote_api=True,
                    max_ocr_tokens=4096,
                    max_ocr_output_tokens=4096,
                    save_markdown=save_markdown,
                    enhanced_table_mode=enhanced_table_mode,
                    use_original_ocr_fallback=True
                )
            else:
                # Use table-aware remote API mode
                from pdf_craft.remote_api.table_aware_parser import TableAwarePageParser
                
                table_parser = TableAwarePageParser()
                page_results = []
                total_input_tokens = 0
                total_output_tokens = 0
                
                for page_num in valid_pages:
                    try:
                        markdown_content, page_metering = table_parser.process_page(
                            pdf_path=pdf_path,
                            page_num=page_num,
                            max_ocr_output_tokens=4096,
                            enhanced_table_mode=enhanced_table_mode
                        )
                        
                        total_input_tokens += page_metering.input_tokens
                        total_output_tokens += page_metering.output_tokens
                        
                        # Save markdown file if requested
                        file_path = None
                        if save_markdown:
                            # Use the same output structure as before
                            output_basename = f"{Path(pdf_path).stem}_{hash(str(Path(pdf_path).stat().st_mtime))[:6]}"
                            output_md_dir = Path(f"/outputs_md/{output_basename}")
                            output_md_dir.mkdir(parents=True, exist_ok=True)
                            
                            md_filename = f"{Path(pdf_path).stem}_{page_num}.md"
                            file_path = output_md_dir / md_filename
                            
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(markdown_content)
                            
                            file_path = str(file_path)
                        
                        page_result = {
                            "page_number": page_num,
                            "markdown_content": markdown_content,
                            "file_path": file_path
                        }
                        page_results.append(page_result)
                        
                    except Exception as e:
                        # Handle page processing error
                        error_content = f"# Page {page_num}\n\nError processing page: {str(e)}"
                        page_result = {
                            "page_number": page_num,
                            "markdown_content": error_content,
                            "file_path": None
                        }
                        page_results.append(page_result)
                
                # Create metering object
                from pdf_craft.metering import OCRTokensMetering
                metering = OCRTokensMetering(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens
                )
            
            # page_results already contains the structured data we need
            selected_pages = page_results
            
            message_parts = []
            if valid_pages:
                message_parts.append(f"Successfully parsed specified pages: {len(valid_pages)} pages")
            
            if invalid_pages:
                message_parts.append(f"Ignored invalid page numbers: {invalid_pages}")
        
        else:
            # Choose processing method based on mode
            if use_hybrid_mode:
                # Use hybrid mode (original structure detection + remote API)
                page_results, metering = transform_pages_markdown_hybrid(
                    pdf_path=pdf_path,
                    pages=None,
                    markdown_assets_path=assets_path,
                    use_remote_api=True,
                    max_ocr_tokens=4096,
                    max_ocr_output_tokens=4096,
                    save_markdown=save_markdown,
                    enhanced_table_mode=enhanced_table_mode,
                    use_original_ocr_fallback=True
                )
            else:
                # Use pure remote API mode
                page_results, metering = transform_pages_markdown(
                    pdf_path=pdf_path,
                    pages=None,
                    markdown_assets_path=assets_path,
                    use_remote_api=True,
                    max_ocr_tokens=4096,
                    max_ocr_output_tokens=4096,
                    save_markdown=save_markdown,
                    enhanced_table_mode=enhanced_table_mode
                )
            
            # page_results already contains the structured data we need
            selected_pages = page_results
            message_parts = ["Successfully parsed all pages"]
        
        # Calculate duration
        duration_seconds = round(time.time() - start_time, 2)
        
        # Build return result
        result = {
            'success': True,
            'pdf_path': pdf_path,
            'total_pages': total_pdf_pages,
            'processed_pages': len(selected_pages),
            'pages': selected_pages,
            'metering': {
                'input_tokens': metering.input_tokens,
                'output_tokens': metering.output_tokens
            },
            'assets_path': str(assets_path),
            'duration_seconds': duration_seconds,
            'message': '; '.join(message_parts)
        }
        
        return jsonify(result)
    
    except Exception as e:
        import traceback
        duration_seconds = round(time.time() - start_time, 2)
        
        # Log detailed error information
        error_details = {
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc(),
            'success': False,
            'duration_seconds': duration_seconds
        }
        
        # Print to server log
        print(f"API Error: {error_details}")
        
        return jsonify(error_details), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration information"""
    try:
        config = load_config()
        return jsonify({
            'success': True,
            'config': {
                'base_url': config.base_url,
                'default_model': config.default_model,
                'api_key_configured': bool(config.api_key),
                'timeout': getattr(config, 'timeout', 120),
                'max_retries': getattr(config, 'max_retries', 1),
            },
            'supported_ocr_sizes': ['tiny', 'small', 'base', 'large', 'gundam']
        })
    except Exception as e:
        return jsonify({
            'error': f'Failed to load config: {str(e)}',
            'success': False
        }), 500


if __name__ == '__main__':
    # Development mode
    app.run(host='0.0.0.0', port=1157, debug=True)