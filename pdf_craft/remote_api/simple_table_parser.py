"""
Simplified table parser that handles low-quality OCR results better
"""

import re
from pathlib import Path
from typing import List, Tuple, Union, Optional, Any, Dict
from os import PathLike

from PIL import Image

from ..pdf.handler import DefaultPDFHandler
from ..metering import OCRTokensMetering
from .client import AIAPIClient
from .config import load_config


class SimpleTableParser:
    """
    Simplified parser that's more tolerant of poor OCR quality
    """
    
    def __init__(self, api_client: Optional[AIAPIClient] = None):
        if api_client is None:
            config = load_config()
            api_client = AIAPIClient(config)
        self._api_client = api_client
        self._pdf_handler = DefaultPDFHandler()

    def process_page(
        self,
        pdf_path: Union[PathLike, str],
        page_num: int,
        max_ocr_output_tokens: Optional[int] = None,
        enhanced_table_mode: bool = True,
    ) -> Tuple[str, OCRTokensMetering]:
        """
        Process a single page with simplified, robust parsing
        """
        pdf_path = Path(pdf_path)
        metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        try:
            # 1. Render page image
            document = self._pdf_handler.open(pdf_path)
            try:
                page_image = document.render_page(page_num, dpi=200)
                if not isinstance(page_image, Image.Image):
                    return f"# Page {page_num}\n\nFailed to render page.", metering
            finally:
                document.close()
            
            # 2. Try multiple API strategies
            markdown_content = None
            
            # Strategy 1: Enhanced table mode
            if enhanced_table_mode:
                try:
                    content, page_metering = self._try_api_call(page_image, max_ocr_output_tokens, True)
                    metering.input_tokens += page_metering.input_tokens
                    metering.output_tokens += page_metering.output_tokens
                    
                    if content and len(content.strip()) > 10:
                        markdown_content = self._format_content(content, page_num, "enhanced")
                except Exception as e:
                    print(f"Enhanced mode failed: {e}")
            
            # Strategy 2: Standard mode fallback
            if not markdown_content:
                try:
                    content, page_metering = self._try_api_call(page_image, max_ocr_output_tokens, False)
                    metering.input_tokens += page_metering.input_tokens
                    metering.output_tokens += page_metering.output_tokens
                    
                    if content and len(content.strip()) > 5:
                        markdown_content = self._format_content(content, page_num, "standard")
                except Exception as e:
                    print(f"Standard mode failed: {e}")
            
            # Strategy 3: Simple text extraction
            if not markdown_content:
                try:
                    content, page_metering = self._try_simple_text_call(page_image, max_ocr_output_tokens)
                    metering.input_tokens += page_metering.input_tokens
                    metering.output_tokens += page_metering.output_tokens
                    
                    if content:
                        markdown_content = self._format_content(content, page_num, "simple")
                except Exception as e:
                    print(f"Simple mode failed: {e}")
            
            # Final fallback
            if not markdown_content:
                markdown_content = f"# Page {page_num}\n\nNo content could be extracted from this page."
            
            return markdown_content, metering
            
        except Exception as e:
            error_msg = f"# Page {page_num}\n\nError: {str(e)}"
            return error_msg, metering

    def _try_api_call(
        self, 
        image: Image.Image, 
        max_tokens: Optional[int],
        enhanced_table_mode: bool
    ) -> Tuple[str, OCRTokensMetering]:
        """Try API call with specific settings"""
        
        response = self._api_client.recognize_image(
            image=image,
            max_tokens=max_tokens or 4096,
            enhanced_table_mode=enhanced_table_mode
        )
        
        content = self._api_client.extract_text_content(response)
        usage = self._api_client.get_usage_info(response)
        
        metering = OCRTokensMetering(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0)
        )
        
        return content, metering

    def _try_simple_text_call(
        self, 
        image: Image.Image, 
        max_tokens: Optional[int]
    ) -> Tuple[str, OCRTokensMetering]:
        """Try with very simple prompt"""
        
        # Override the API client's prompt temporarily
        original_method = self._api_client.recognize_image
        
        def simple_recognize(image, max_tokens=None, **kwargs):
            # Use a very simple prompt
            return self._api_client._make_request({
                "model": self._api_client.config.default_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{self._api_client._image_to_base64(image)}"
                                }
                            },
                            {
                                "type": "text",
                                "text": "请提取图片中的所有文字内容，保持原有格式。"
                            }
                        ]
                    }
                ],
                "stream": False,
                "max_tokens": max_tokens or 2048,
                "temperature": 0.1,
            })
        
        response = simple_recognize(image, max_tokens)
        content = self._api_client.extract_text_content(response)
        usage = self._api_client.get_usage_info(response)
        
        metering = OCRTokensMetering(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0)
        )
        
        return content, metering

    def _format_content(self, content: str, page_num: int, mode: str) -> str:
        """Format content into markdown with intelligent table detection"""
        
        if not content or not content.strip():
            return f"# Page {page_num}\n\n*No content extracted*"
        
        # Clean up content
        content = content.strip()
        
        # Try to detect and format tables
        formatted_content = self._smart_format_content(content)
        
        # Add page header and mode info
        header = f"# Page {page_num}"
        if mode != "enhanced":
            header += f" *(extracted using {mode} mode)*"
        
        return f"{header}\n\n{formatted_content}"

    def _smart_format_content(self, content: str) -> str:
        """Smart formatting that tries to preserve table structure"""
        
        # If content contains pipe characters, assume it's already table format
        if '|' in content and content.count('|') >= 4:
            return self._clean_markdown_table(content)
        
        # If content has HTML table tags, preserve them
        if '<table>' in content.lower():
            return content
        
        # Try to detect key-value pairs and format as table
        if self._has_key_value_structure(content):
            return self._format_key_value_as_table(content)
        
        # For other content, apply basic formatting
        return self._apply_basic_formatting(content)

    def _clean_markdown_table(self, content: str) -> str:
        """Clean up markdown table formatting"""
        lines = content.split('\n')
        table_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if table_lines and not table_lines[-1].strip():
                    continue  # Skip multiple empty lines
                table_lines.append('')
                continue
            
            # If line contains pipes, format as table row
            if '|' in line:
                # Ensure proper table formatting
                if not line.startswith('|'):
                    line = '|' + line
                if not line.endswith('|'):
                    line = line + '|'
                
                # Clean up cell spacing
                cells = line.split('|')[1:-1]  # Remove first and last empty elements
                cells = [cell.strip() for cell in cells]
                line = '| ' + ' | '.join(cells) + ' |'
            
            table_lines.append(line)
        
        return '\n'.join(table_lines)

    def _has_key_value_structure(self, content: str) -> bool:
        """Check if content looks like key-value pairs"""
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        if len(lines) < 2:
            return False
        
        kv_count = 0
        for line in lines:
            if ':' in line or '：' in line:
                kv_count += 1
        
        return (kv_count / len(lines)) > 0.5

    def _format_key_value_as_table(self, content: str) -> str:
        """Format key-value content as a table"""
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        # Add table header
        table_lines = ['| 项目 | 值 |', '|------|-----|']
        
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                table_lines.append(f'| {key} | {value} |')
            elif '：' in line:
                key, value = line.split('：', 1)
                key = key.strip()
                value = value.strip()
                table_lines.append(f'| {key} | {value} |')
            else:
                # Non-key-value line, add as spanning row
                table_lines.append(f'| {line} | |')
        
        return '\n'.join(table_lines)

    def _apply_basic_formatting(self, content: str) -> str:
        """Apply basic markdown formatting to content"""
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines in output
            if not line:
                if formatted_lines and formatted_lines[-1] != '':
                    formatted_lines.append('')
                continue
            
            # Check if line looks like a title
            if self._looks_like_title(line):
                formatted_lines.append(f'## {line}')
            else:
                formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)

    def _looks_like_title(self, line: str) -> bool:
        """Check if a line looks like a title"""
        # Very basic title detection
        if len(line) < 50 and not line.endswith('.') and not ':' in line:
            # Check for title indicators
            title_words = ['表', 'table', '图', 'figure', '第', 'chapter', '章节']
            for word in title_words:
                if word in line.lower():
                    return True
        
        return False