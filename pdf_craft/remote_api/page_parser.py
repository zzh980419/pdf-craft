"""
Page-based PDF parsing functionality using remote API
"""

import os
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple, Union, Dict, Any
from os import PathLike

from ..pdf import DefaultPDFHandler, OCR
from ..metering import OCRTokensMetering
from .client import AIAPIClient
from .config import load_config


def _generate_file_fingerprint(pdf_path: Path) -> str:
    """
    Generate 6-digit fingerprint for PDF file based on file size and modification time
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        6-digit hex string fingerprint
    """
    try:
        stat = pdf_path.stat()
        # Use file size and modification time to generate fingerprint
        content = f"{stat.st_size}_{stat.st_mtime}"
        hash_obj = hashlib.md5(content.encode())
        return hash_obj.hexdigest()[:6]
    except:
        # Fallback to simple hash of filename
        return hashlib.md5(pdf_path.name.encode()).hexdigest()[:6]


def _get_pdf_basename(pdf_path: Union[str, Path]) -> str:
    """
    Extract PDF filename without extension from path
    
    Args:
        pdf_path: Path to PDF file (can be absolute or relative)
        
    Returns:
        Filename without extension
    """
    return Path(pdf_path).stem


class PageTransform:
    """Page-based PDF to Markdown transformer using remote API"""
    
    def __init__(
        self,
        models_cache_path: Optional[Union[PathLike, str]] = None,
        pdf_handler: Optional[DefaultPDFHandler] = None,
        local_only: bool = False,
        api_client: Optional[AIAPIClient] = None,
    ) -> None:
        """Initialize PageTransform
        
        Args:
            models_cache_path: Path to model cache (not used with remote API)
            pdf_handler: PDF handler instance
            local_only: Whether to use local models only (forced to False)
            api_client: Remote API client instance
        """
        # Force remote API mode
        self._local_only = False
        
        # Initialize API client
        if api_client is None:
            config = load_config()
            api_client = AIAPIClient(config)
        self._api_client = api_client
        
        # Initialize PDF handler
        self._pdf_handler = pdf_handler or DefaultPDFHandler()
        
        # Initialize OCR with remote API
        self._ocr = OCR(
            model_path=models_cache_path,
            pdf_handler=self._pdf_handler,
            local_only=False,
        )

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
        Transform PDF pages to Markdown using remote API
        
        Args:
            pdf_path: Path to PDF file
            pages: List of page numbers to process (1-based). If None, process all pages
            markdown_assets_path: Path to store markdown assets
            max_ocr_tokens: Maximum OCR input tokens
            max_ocr_output_tokens: Maximum OCR output tokens
            save_markdown: Whether to save markdown files to disk
            enhanced_table_mode: Whether to use enhanced table recognition prompts
            **kwargs: Additional arguments (ignored)
            
        Returns:
            Tuple of (list of page info dicts, metering info)
            Page info dict contains: page_number, markdown_content, file_path (if saved)
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
            # Process all pages
            pages_to_process = list(range(1, total_pages + 1))
        else:
            # Validate and filter page numbers
            pages_to_process = []
            for page_num in pages:
                if isinstance(page_num, int) and 1 <= page_num <= total_pages:
                    pages_to_process.append(page_num)
            
            if not pages_to_process:
                raise ValueError(f"No valid pages specified. PDF has {total_pages} pages.")
        
        # Create markdown assets directory if specified
        assets_path = None
        if markdown_assets_path:
            assets_path = Path(markdown_assets_path)
            assets_path.mkdir(parents=True, exist_ok=True)
        
        # Setup output directory for markdown files if save_markdown is True
        output_dir = None
        pdf_basename = None
        if save_markdown:
            pdf_basename = _get_pdf_basename(pdf_path)
            file_fingerprint = _generate_file_fingerprint(pdf_path)
            output_dir_name = f"{pdf_basename}_{file_fingerprint}"
            
            # Get output base directory from environment variable, fallback to 'outputs'
            output_base_dir = os.getenv("MD_OUTPUT_DIR", "outputs")
            output_dir = Path(output_base_dir) / output_dir_name
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each page individually
        page_results = []
        total_metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        for page_num in pages_to_process:
            try:
                # Extract and process single page
                page_markdown, page_metering = self._process_single_page(
                    pdf_path=pdf_path,
                    page_num=page_num,
                    assets_path=assets_path,
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

    def _process_single_page(
        self,
        pdf_path: Path,
        page_num: int,
        assets_path: Optional[Path],
        max_ocr_output_tokens: int,
        enhanced_table_mode: bool = True
    ) -> Tuple[str, OCRTokensMetering]:
        """Process a single PDF page
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number to process (1-based)
            assets_path: Path to save assets
            max_ocr_output_tokens: Maximum output tokens for OCR
            enhanced_table_mode: Whether to use enhanced table recognition
            
        Returns:
            Tuple of (markdown content, metering info)
        """
        from PIL import Image
        
        metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        try:
            # Open PDF and extract page
            document = self._pdf_handler.open(pdf_path)
            try:
                # Check page range
                if page_num > document.pages_count:
                    return f"# Page {page_num}\n\nPage number out of range.", metering
                
                # Render page to image (pdf2image uses 1-based page numbers)
                page_image = document.render_page(page_num, dpi=150)  # Use 150 DPI for good quality
                if not isinstance(page_image, Image.Image):
                    return f"# Page {page_num}\n\nFailed to render page image.", metering
                
                # Use remote API to recognize image content
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
                
                # Save page image as asset if assets path is provided
                if assets_path:
                    assets_path.mkdir(parents=True, exist_ok=True)
                    image_path = assets_path / f"page_{page_num}.jpg"
                    page_image.save(image_path, "JPEG", quality=85)
                
                # Format as markdown with page header
                formatted_markdown = f"# Page {page_num}\n\n{markdown_content}"
                
                return formatted_markdown, metering
                
            finally:
                document.close()
                
        except Exception as e:
            error_msg = f"# Page {page_num}\n\nError during OCR processing: {str(e)}"
            return error_msg, metering


def transform_pages_markdown(
    pdf_path: Union[PathLike, str],
    pages: Optional[List[int]] = None,
    markdown_assets_path: Optional[Union[PathLike, str]] = None,
    use_remote_api: bool = True,
    max_ocr_tokens: Optional[int] = None,
    max_ocr_output_tokens: Optional[int] = None,
    api_client: Optional[AIAPIClient] = None,
    save_markdown: bool = False,
    enhanced_table_mode: bool = True,
    **kwargs
) -> Tuple[List[Dict[str, Any]], OCRTokensMetering]:
    """
    Transform PDF pages to Markdown using remote API
    
    Args:
        pdf_path: Path to PDF file
        pages: List of page numbers to process (1-based). If None, process all pages
        markdown_assets_path: Path to store markdown assets
        use_remote_api: Whether to use remote API (always True for this implementation)
        max_ocr_tokens: Maximum OCR tokens
        max_ocr_output_tokens: Maximum OCR output tokens
        api_client: Custom API client instance
        save_markdown: Whether to save markdown files to disk
        enhanced_table_mode: Whether to use enhanced table recognition prompts
        **kwargs: Additional arguments
        
    Returns:
        Tuple of (list of page info dicts, metering info)
        Page info dict contains: page_number, markdown_content, file_path (if saved)
    """
    # Create PageTransform instance
    page_transform = PageTransform(
        models_cache_path=None,
        pdf_handler=None,
        local_only=False,
        api_client=api_client,
    )
    
    # Transform pages
    return page_transform.transform_pages_to_markdown(
        pdf_path=pdf_path,
        pages=pages,
        markdown_assets_path=markdown_assets_path,
        max_ocr_tokens=max_ocr_tokens,
        max_ocr_output_tokens=max_ocr_output_tokens,
        save_markdown=save_markdown,
        enhanced_table_mode=enhanced_table_mode,
        **kwargs
    )


def validate_pdf_path(pdf_path: str) -> Tuple[bool, str]:
    """
    Validate PDF file path
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not pdf_path:
        return False, "PDF path is required"
    
    path = Path(pdf_path)
    
    if not path.exists():
        return False, f"PDF file not found: {pdf_path}"
    
    if not path.is_file():
        return False, f"Path is not a file: {pdf_path}"
    
    if path.suffix.lower() != '.pdf':
        return False, f"File is not a PDF: {pdf_path}"
    
    return True, ""