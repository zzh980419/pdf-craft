"""
Simple transform function that replaces original project's transform with remote API
"""

from pathlib import Path
from typing import Optional, Union, List
from os import PathLike

from .remote_ocr import RemoteOCR
from ..pdf import DefaultPDFHandler
from ..metering import OCRTokensMetering


def transform_pdf_to_markdown_remote(
    pdf_path: Union[PathLike, str],
    output_dir: Union[PathLike, str],
    pages: Optional[List[int]] = None,
    **kwargs
) -> OCRTokensMetering:
    """
    Transform PDF to markdown using remote API
    
    This function has the same interface as the original project's transform function,
    but uses remote API instead of local models.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Output directory for markdown and assets
        pages: List of page numbers to process (1-indexed), None for all pages
        **kwargs: Additional parameters (for compatibility)
        
    Returns:
        OCRTokensMetering: Token usage information
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    
    # Create output directories
    ocr_path = output_dir / "ocr"
    asset_path = output_dir / "assets"
    markdown_path = output_dir / "markdown"
    
    ocr_path.mkdir(parents=True, exist_ok=True)
    asset_path.mkdir(parents=True, exist_ok=True)
    markdown_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize remote OCR
    remote_ocr = RemoteOCR(
        model_path=None,  # Not used for remote API
        pdf_handler=DefaultPDFHandler(),
        local_only=False,  # We're using remote API
    )
    
    # Determine page indexes to process
    if pages is not None:
        page_indexes = set(pages)
    else:
        # Process all pages
        import sys
        page_indexes = range(1, sys.maxsize)
    
    # Run OCR
    total_input_tokens = 0
    total_output_tokens = 0
    
    for event in remote_ocr.recognize(
        pdf_path=pdf_path,
        asset_path=asset_path,
        ocr_path=ocr_path,
        ocr_size="gundam",
        page_indexes=page_indexes,
        **kwargs
    ):
        if hasattr(event, 'input_tokens') and hasattr(event, 'output_tokens'):
            total_input_tokens += event.input_tokens
            total_output_tokens += event.output_tokens
        
        # Print progress (optional)
        if event.kind.name == 'START':
            print(f"Processing page {event.page_index}/{event.total_pages}...")
        elif event.kind.name == 'COMPLETE':
            print(f"✓ Page {event.page_index} completed")
        elif event.kind.name == 'FAILED':
            print(f"✗ Page {event.page_index} failed: {event.error}")
    
    # Generate markdown files from OCR results
    _generate_markdown_files(ocr_path, markdown_path, asset_path)
    
    return OCRTokensMetering(
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens
    )


def _generate_markdown_files(ocr_path: Path, markdown_path: Path, asset_path: Path):
    """Generate markdown files from OCR XML results"""
    from ..common import read_xml
    from ..pdf.types import decode
    
    # Process each XML file
    for xml_file in ocr_path.glob("page_*.xml"):
        try:
            # Extract page number from filename
            page_num = int(xml_file.stem.split('_')[1])
            
            # Read and decode page data
            page_element = read_xml(xml_file)
            page_data = decode(page_element)
            
            # Convert to simple markdown
            markdown_content = f"# Page {page_num}\n\n"
            
            # Add body layouts
            for layout in page_data.body_layouts:
                if layout.text and layout.text.strip():
                    # Simple text formatting based on ref type
                    if layout.ref == "table":
                        markdown_content += _format_as_table(layout.text)
                    elif layout.ref in ["title", "heading"]:
                        markdown_content += f"## {layout.text}\n\n"
                    else:
                        markdown_content += f"{layout.text}\n\n"
                
                # Add images if present
                if layout.hash:
                    asset_file = asset_path / f"{layout.hash}.png"
                    if asset_file.exists():
                        markdown_content += f"![{layout.ref}]({asset_file.name})\n\n"
            
            # Save markdown file
            md_file = markdown_path / f"page_{page_num}.md"
            md_file.write_text(markdown_content, encoding='utf-8')
            
        except Exception as e:
            print(f"Warning: Failed to process {xml_file}: {e}")


def _format_as_table(text: str) -> str:
    """Simple table formatting for markdown"""
    lines = text.strip().split('\n')
    
    # If text contains pipe characters, assume it's already table format
    if '|' in text:
        return text + "\n\n"
    
    # Simple key-value pair formatting
    if len(lines) > 1:
        formatted_lines = []
        for i, line in enumerate(lines):
            if ':' in line or '：' in line:
                parts = line.replace('：', ':').split(':', 1)
                if len(parts) == 2:
                    key, value = parts[0].strip(), parts[1].strip()
                    if i == 0:
                        formatted_lines.append(f"| {key} | {value} |")
                        formatted_lines.append("|---|---|")
                    else:
                        formatted_lines.append(f"| {key} | {value} |")
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)
        
        if formatted_lines and '|' in formatted_lines[0]:
            return '\n'.join(formatted_lines) + "\n\n"
    
    # Default: return as-is
    return text + "\n\n"