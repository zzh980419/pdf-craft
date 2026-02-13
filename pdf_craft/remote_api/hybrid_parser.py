"""
Hybrid PDF parser that combines original table processing with remote API
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple, Union, Dict, Any
from os import PathLike

from ..pdf import DefaultPDFHandler, OCR
from ..pdf.page_extractor import PageExtractorNode
from ..common import AssetHub
from ..metering import OCRTokensMetering
from ..error import IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker
from .client import AIAPIClient
from .config import load_config


class HybridPageTransform:
    """
    Hybrid PDF to Markdown transformer that combines:
    - Original project's table detection and structure extraction
    - Remote API for text recognition
    """
    
    def __init__(
        self,
        models_cache_path: Optional[Union[PathLike, str]] = None,
        pdf_handler: Optional[DefaultPDFHandler] = None,
        local_only: bool = False,
        api_client: Optional[AIAPIClient] = None,
        use_original_ocr: bool = False,
    ) -> None:
        """Initialize HybridPageTransform
        
        Args:
            models_cache_path: Path to model cache
            pdf_handler: PDF handler instance
            local_only: Whether to use local models only
            api_client: Remote API client instance
            use_original_ocr: Whether to fallback to original OCR for complex content
        """
        # Initialize API client
        if api_client is None:
            config = load_config()
            api_client = AIAPIClient(config)
        self._api_client = api_client
        
        # Initialize PDF handler
        self._pdf_handler = pdf_handler or DefaultPDFHandler()
        
        # Initialize original OCR (for fallback)
        self._original_ocr = None
        if use_original_ocr:
            self._original_ocr = OCR(
                model_path=models_cache_path,
                pdf_handler=self._pdf_handler,
                local_only=local_only,
            )
        
        # Initialize page extractor (for structure detection)
        self._page_extractor_node = None
        self._has_doc_page_extractor = False
        
        try:
            # Check if doc_page_extractor is available
            import doc_page_extractor
            self._has_doc_page_extractor = True
            
            # Only try to initialize if the package is available
            try:
                self._page_extractor_node = PageExtractorNode(
                    model_path=models_cache_path,
                    local_only=local_only,
                )
                print("Successfully initialized PageExtractorNode")
            except Exception as init_error:
                print(f"Warning: Could not initialize PageExtractorNode: {init_error}")
                print("Will still try to use doc_page_extractor directly")
                
        except ImportError:
            print("Warning: doc_page_extractor not available.")
            print("Install it with: pip install doc-page-extractor")
            print("Falling back to remote API only mode")

    def transform_pages_to_markdown(
        self,
        pdf_path: Union[PathLike, str],
        pages: Optional[List[int]] = None,
        markdown_assets_path: Optional[Union[PathLike, str]] = None,
        max_ocr_tokens: Optional[int] = None,
        max_ocr_output_tokens: Optional[int] = None,
        save_markdown: bool = False,
        enhanced_table_mode: bool = True,
        **kwargs
    ) -> Tuple[List[Dict[str, Any]], OCRTokensMetering]:
        """
        Transform PDF pages to Markdown using hybrid approach
        """
        # Convert to Path object
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Get PDF total pages
        document = self._pdf_handler.open(pdf_path)
        try:
            total_pages = document.pages_count
        finally:
            document.close()
        
        # Determine which pages to process
        if pages is None:
            pages_to_process = list(range(1, total_pages + 1))
        else:
            pages_to_process = []
            for page_num in pages:
                if isinstance(page_num, int) and 1 <= page_num <= total_pages:
                    pages_to_process.append(page_num)
            
            if not pages_to_process:
                raise ValueError(f"No valid pages specified. PDF has {total_pages} pages.")
        
        # Setup output directory for markdown files if save_markdown is True
        output_dir = None
        pdf_basename = None
        if save_markdown:
            from .page_parser import _get_pdf_basename, _generate_file_fingerprint
            pdf_basename = _get_pdf_basename(pdf_path)
            file_fingerprint = _generate_file_fingerprint(pdf_path)
            output_dir_name = f"{pdf_basename}_{file_fingerprint}"
            
            output_base_dir = os.getenv("MD_OUTPUT_DIR", "outputs")
            output_dir = Path(output_base_dir) / output_dir_name
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each page
        page_results = []
        total_metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        for page_num in pages_to_process:
            try:
                if self._has_doc_page_extractor and self._original_ocr:
                    # Try original OCR first (better for tables)
                    page_markdown, page_metering = self._process_page_with_original_ocr(
                        pdf_path=pdf_path,
                        page_num=page_num,
                        markdown_assets_path=markdown_assets_path,
                        max_ocr_output_tokens=max_ocr_output_tokens or 4096
                    )
                elif self._page_extractor_node:
                    # Use hybrid approach with structure detection
                    page_markdown, page_metering = self._process_page_hybrid(
                        pdf_path=pdf_path,
                        page_num=page_num,
                        markdown_assets_path=markdown_assets_path,
                        max_ocr_output_tokens=max_ocr_output_tokens or 4096,
                        enhanced_table_mode=enhanced_table_mode
                    )
                else:
                    # Fallback to simple remote API
                    from .page_parser import PageTransform
                    simple_transform = PageTransform(
                        models_cache_path=None,
                        pdf_handler=self._pdf_handler,
                        api_client=self._api_client
                    )
                    page_markdown, page_metering = simple_transform._process_single_page(
                        pdf_path=pdf_path,
                        page_num=page_num,
                        assets_path=Path(markdown_assets_path) if markdown_assets_path else None,
                        max_ocr_output_tokens=max_ocr_output_tokens or 4096,
                        enhanced_table_mode=enhanced_table_mode
                    )
                
                # Create page result dict
                page_result = {
                    "page_number": page_num,
                    "markdown_content": page_markdown
                }
                
                # Save markdown file if requested
                if save_markdown and output_dir and pdf_basename:
                    md_filename = f"{pdf_basename}_{page_num}.md"
                    md_file_path = output_dir / md_filename
                    
                    try:
                        with open(md_file_path, 'w', encoding='utf-8') as f:
                            f.write(page_markdown)
                        page_result["file_path"] = str(md_file_path.absolute())
                    except Exception as e:
                        print(f"Warning: Failed to save markdown file for page {page_num}: {e}")
                        page_result["file_path"] = None
                else:
                    page_result["file_path"] = None
                
                page_results.append(page_result)
                total_metering.input_tokens += page_metering.input_tokens
                total_metering.output_tokens += page_metering.output_tokens
                
            except Exception as e:
                print(f"Error processing page {page_num}: {e}")
                error_page_result = {
                    "page_number": page_num,
                    "markdown_content": f"# Page {page_num}\n\nError during processing: {str(e)}",
                    "file_path": None
                }
                page_results.append(error_page_result)
        
        return page_results, total_metering

    def _process_page_with_original_ocr(
        self,
        pdf_path: Path,
        page_num: int,
        markdown_assets_path: Optional[Union[PathLike, str]],
        max_ocr_output_tokens: int
    ) -> Tuple[str, OCRTokensMetering]:
        """
        Process a single page using original OCR for better table handling
        """
        from tempfile import TemporaryDirectory
        from ..common import AssetHub
        from ..metering import OCRTokensMetering
        
        metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        if not self._original_ocr:
            return f"# Page {page_num}\n\nOriginal OCR not available.", metering
        
        try:
            # Create temporary directories for original OCR processing
            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                ocr_path = temp_path / "ocr"
                asset_path = temp_path / "assets"
                
                ocr_path.mkdir(parents=True, exist_ok=True)
                asset_path.mkdir(parents=True, exist_ok=True)
                
                # Use original OCR to process single page
                events = list(self._original_ocr.recognize(
                    pdf_path=pdf_path,
                    asset_path=asset_path,
                    ocr_path=ocr_path,
                    ocr_size="gundam",  # Use highest quality for table recognition
                    dpi=300,
                    includes_footnotes=False,
                    page_indexes=[page_num],  # Process only the specific page
                    max_tokens=None,
                    max_output_tokens=max_ocr_output_tokens,
                    device_number=None,
                ))
                
                # Check if processing was successful
                successful_events = [e for e in events if hasattr(e, 'kind') and e.kind.name == 'COMPLETE']
                
                if not successful_events:
                    # If original OCR failed, fallback to remote API
                    return self._fallback_to_remote_api(pdf_path, page_num, max_ocr_output_tokens)
                
                # Get token usage from events
                for event in events:
                    if hasattr(event, 'input_tokens') and hasattr(event, 'output_tokens'):
                        metering.input_tokens += event.input_tokens
                        metering.output_tokens += event.output_tokens
                
                # Read the generated XML file and convert to markdown
                xml_file = ocr_path / f"page_{page_num}.xml"
                if xml_file.exists():
                    # Convert XML to markdown using simplified approach
                    from ..common import read_xml
                    from ..pdf.types import decode
                    
                    page_element = read_xml(xml_file)
                    page_data = decode(page_element)
                    
                    # Create asset hub for the target location
                    if markdown_assets_path:
                        target_asset_hub = AssetHub(Path(markdown_assets_path))
                        target_asset_hub.path.mkdir(parents=True, exist_ok=True)
                        # Copy assets from temp location to target location
                        import shutil
                        for asset_file in asset_path.glob("*"):
                            if asset_file.is_file():
                                shutil.copy2(asset_file, target_asset_hub.path)
                    else:
                        target_asset_hub = AssetHub(asset_path)
                    
                    # Simple markdown conversion from page layouts
                    markdown_content = self._convert_page_to_markdown(page_data, target_asset_hub)
                    
                    # Add page header
                    formatted_markdown = f"# Page {page_num}\n\n{markdown_content}"
                    
                    return formatted_markdown, metering
                else:
                    return f"# Page {page_num}\n\nOriginal OCR processing failed - no output generated.", metering
                    
        except Exception as e:
            # If original OCR fails, fallback to remote API
            print(f"Original OCR failed for page {page_num}: {e}")
            return self._fallback_to_remote_api(pdf_path, page_num, max_ocr_output_tokens)

    def _convert_page_to_markdown(self, page_data, asset_hub: AssetHub) -> str:
        """
        Convert page data to markdown format
        """
        markdown_parts = []
        
        # Process body layouts
        for layout in page_data.body_layouts:
            content = self._convert_layout_to_markdown(layout, asset_hub)
            if content.strip():
                markdown_parts.append(content)
        
        # Process footnotes if any
        if page_data.footnotes_layouts:
            markdown_parts.append("\n---\n")  # Separator for footnotes
            markdown_parts.append("**Footnotes:**\n")
            for layout in page_data.footnotes_layouts:
                content = self._convert_layout_to_markdown(layout, asset_hub)
                if content.strip():
                    markdown_parts.append(content)
        
        return "\n\n".join(markdown_parts)

    def _convert_layout_to_markdown(self, layout, asset_hub: AssetHub) -> str:
        """
        Convert a single layout to markdown
        """
        # Handle different layout types
        ref = getattr(layout, 'ref', '')
        text = getattr(layout, 'text', '')
        hash_value = getattr(layout, 'hash', None)
        
        # Handle images and assets
        if hash_value and ref in ['image', 'figure', 'chart', 'table_image']:
            # Construct asset file path
            asset_file_path = asset_hub._asset_path / f"{hash_value}.png"
            if asset_file_path.exists():
                relative_path = asset_file_path.name
                return f"![{ref}]({relative_path})"
            else:
                return f"[{ref}: {hash_value}]"
        
        # Handle tables
        elif ref == 'table' and text:
            # Try to format as markdown table
            lines = text.strip().split('\n')
            if len(lines) > 1:
                # Simple table formatting
                table_lines = []
                for i, line in enumerate(lines):
                    # Clean and split line
                    cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                    if cells:
                        table_lines.append('| ' + ' | '.join(cells) + ' |')
                        # Add header separator after first row
                        if i == 0:
                            table_lines.append('|' + '---|' * len(cells))
                return '\n'.join(table_lines)
            else:
                return text
        
        # Handle titles and headings
        elif ref in ['title', 'subtitle', 'heading']:
            if text:
                # Determine heading level based on ref type
                if ref == 'title':
                    return f"## {text}"
                elif ref == 'subtitle':
                    return f"### {text}"
                else:
                    return f"#### {text}"
            
        # Handle regular text
        elif ref in ['text', 'paragraph'] and text:
            return text
            
        # Handle other content
        elif text:
            return text
        
        return ""

    def _process_page_hybrid(
        self,
        pdf_path: Path,
        page_num: int,
        markdown_assets_path: Optional[Union[PathLike, str]],
        max_ocr_output_tokens: int,
        enhanced_table_mode: bool = True
    ) -> Tuple[str, OCRTokensMetering]:
        """
        Process a single page using hybrid approach:
        1. Use original project's structure detection
        2. Use remote API for text recognition
        """
        from PIL import Image
        import tempfile
        
        metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        try:
            # Get page image
            document = self._pdf_handler.open(pdf_path)
            try:
                page_image = document.render_page(page_num, dpi=200)  # Higher DPI for better structure detection
                if not isinstance(page_image, Image.Image):
                    return f"# Page {page_num}\n\nFailed to render page image.", metering
                
                # Try to use original project's structure detection
                try:
                    page_content = self._extract_page_with_structure(
                        page_image, page_num, markdown_assets_path, max_ocr_output_tokens
                    )
                    # For now, we'll get the text recognition from remote API
                    # and combine it with structure info later
                    
                    # Use remote API for text recognition
                    response = self._api_client.recognize_image(
                        image=page_image,
                        max_tokens=max_ocr_output_tokens,
                        enhanced_table_mode=enhanced_table_mode
                    )
                    
                    # Extract text content
                    markdown_content = self._api_client.extract_text_content(response)
                    
                    # Get usage info
                    usage = self._api_client.get_usage_info(response)
                    metering.input_tokens += usage.get("input_tokens", 0)
                    metering.output_tokens += usage.get("output_tokens", 0)
                    
                    # If we got good content from remote API, use it
                    if markdown_content and len(markdown_content.strip()) > 10:
                        formatted_markdown = f"# Page {page_num}\n\n{markdown_content}"
                    else:
                        # If remote API failed, try original OCR as fallback
                        formatted_markdown = self._fallback_to_original_ocr(pdf_path, page_num)
                    
                    return formatted_markdown, metering
                    
                except Exception as structure_error:
                    print(f"Structure detection failed for page {page_num}: {structure_error}")
                    # Fallback to simple remote API
                    response = self._api_client.recognize_image(
                        image=page_image,
                        max_tokens=max_ocr_output_tokens,
                        enhanced_table_mode=enhanced_table_mode
                    )
                    
                    markdown_content = self._api_client.extract_text_content(response)
                    usage = self._api_client.get_usage_info(response)
                    metering.input_tokens += usage.get("input_tokens", 0)
                    metering.output_tokens += usage.get("output_tokens", 0)
                    
                    formatted_markdown = f"# Page {page_num}\n\n{markdown_content}"
                    return formatted_markdown, metering
                
            finally:
                document.close()
                
        except Exception as e:
            error_msg = f"# Page {page_num}\n\nError during hybrid processing: {str(e)}"
            return error_msg, metering

    def _extract_page_with_structure(self, page_image, page_num, markdown_assets_path, max_tokens):
        """
        Use original project's page extractor to detect structure
        This is a simplified version - in practice we'd need to integrate more deeply
        """
        if not self._page_extractor_node:
            raise Exception("PageExtractorNode not available")
        
        # For now, this is a placeholder
        # The actual integration would require more work to properly combine
        # the structure detection with remote text recognition
        
        return None  # Indicate that we should fallback to remote API

    def _fallback_to_remote_api(
        self, 
        pdf_path: Path, 
        page_num: int, 
        max_ocr_output_tokens: int
    ) -> Tuple[str, OCRTokensMetering]:
        """
        Fallback to remote API when original OCR fails
        """
        from PIL import Image
        
        metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        try:
            # Get page image
            document = self._pdf_handler.open(pdf_path)
            try:
                page_image = document.render_page(page_num, dpi=200)
                if not isinstance(page_image, Image.Image):
                    return f"# Page {page_num}\n\nFailed to render page image.", metering
                
                # Use remote API with enhanced table mode
                response = self._api_client.recognize_image(
                    image=page_image,
                    max_tokens=max_ocr_output_tokens,
                    enhanced_table_mode=True
                )
                
                # Extract content and usage
                markdown_content = self._api_client.extract_text_content(response)
                usage = self._api_client.get_usage_info(response)
                metering.input_tokens += usage.get("input_tokens", 0)
                metering.output_tokens += usage.get("output_tokens", 0)
                
                formatted_markdown = f"# Page {page_num}\n\n{markdown_content}"
                return formatted_markdown, metering
                
            finally:
                document.close()
                
        except Exception as e:
            return f"# Page {page_num}\n\nBoth original OCR and remote API failed: {str(e)}", metering

    def _fallback_to_original_ocr(self, pdf_path: Path, page_num: int) -> str:
        """
        Fallback to original OCR when remote API fails (simplified version for hybrid mode)
        """
        if not self._original_ocr:
            return f"# Page {page_num}\n\nRemote API failed and no original OCR available."
        
        try:
            # Try to use the full original OCR method
            markdown_content, _ = self._process_page_with_original_ocr(
                pdf_path, page_num, None, 4096
            )
            return markdown_content
        except Exception as e:
            return f"# Page {page_num}\n\nBoth remote API and original OCR failed: {str(e)}"


def transform_pages_markdown_hybrid(
    pdf_path: Union[PathLike, str],
    pages: Optional[List[int]] = None,
    markdown_assets_path: Optional[Union[PathLike, str]] = None,
    use_remote_api: bool = True,
    max_ocr_tokens: Optional[int] = None,
    max_ocr_output_tokens: Optional[int] = None,
    api_client: Optional[AIAPIClient] = None,
    save_markdown: bool = False,
    enhanced_table_mode: bool = True,
    use_original_ocr_fallback: bool = True,
    **kwargs
) -> Tuple[List[Dict[str, Any]], OCRTokensMetering]:
    """
    Transform PDF pages to Markdown using hybrid approach
    
    This function combines the original project's structure detection
    with remote API text recognition for better table handling.
    """
    # Create HybridPageTransform instance
    hybrid_transform = HybridPageTransform(
        models_cache_path=None,
        pdf_handler=None,
        local_only=False,
        api_client=api_client,
        use_original_ocr=use_original_ocr_fallback,
    )
    
    # Transform pages
    return hybrid_transform.transform_pages_to_markdown(
        pdf_path=pdf_path,
        pages=pages,
        markdown_assets_path=markdown_assets_path,
        max_ocr_tokens=max_ocr_tokens,
        max_ocr_output_tokens=max_ocr_output_tokens,
        save_markdown=save_markdown,
        enhanced_table_mode=enhanced_table_mode,
        **kwargs
    )