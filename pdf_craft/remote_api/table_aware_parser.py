"""
Table-aware parser that integrates remote API with original table processing pipeline
"""

import re
from pathlib import Path
from typing import List, Tuple, Union, Optional, Any, Dict
from os import PathLike

from PIL import Image

from ..pdf.handler import DefaultPDFHandler
from ..pdf.types import Page, PageLayout
from ..metering import OCRTokensMetering
from ..markdown.render.table import render_table_content
from .client import AIAPIClient
from .config import load_config


class TableAwarePageParser:
    """
    Page parser that properly handles tables using original project's table processing logic
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
        Process a single page with table-aware parsing
        
        Returns markdown content with properly rendered tables
        """
        pdf_path = Path(pdf_path)
        metering = OCRTokensMetering(input_tokens=0, output_tokens=0)
        
        try:
            # 1. 渲染页面图像
            document = self._pdf_handler.open(pdf_path)
            try:
                page_image = document.render_page(page_num, dpi=200)
                if not isinstance(page_image, Image.Image):
                    return f"# Page {page_num}\n\nFailed to render page.", metering
            finally:
                document.close()
            
            # 2. 远程API识别
            response = self._api_client.recognize_image(
                image=page_image,
                max_tokens=max_ocr_output_tokens or 4096,
                enhanced_table_mode=enhanced_table_mode
            )
            
            # 3. 提取内容和计量信息
            raw_content = self._api_client.extract_text_content(response)
            usage = self._api_client.get_usage_info(response)
            metering.input_tokens += usage.get("input_tokens", 0)
            metering.output_tokens += usage.get("output_tokens", 0)
            
            if not raw_content or not raw_content.strip():
                return f"# Page {page_num}\n\nNo content recognized.", metering
            
            # 4. 解析内容并创建结构化布局
            page_layouts = self._parse_content_to_layouts(raw_content, page_image.size)
            
            # 5. 渲染为Markdown
            markdown_content = self._render_layouts_to_markdown(page_layouts, page_num)
            
            return markdown_content, metering
            
        except Exception as e:
            error_msg = f"# Page {page_num}\n\nError: {str(e)}"
            return error_msg, metering

    def _parse_content_to_layouts(
        self, 
        content: str, 
        image_size: Tuple[int, int]
    ) -> List[PageLayout]:
        """
        Parse OCR content into structured layouts, detecting tables
        """
        layouts = []
        width, height = image_size
        
        # 分段处理内容
        sections = self._split_content_sections(content)
        
        order = 0
        for section in sections:
            if self._is_table_section(section):
                # 创建表格布局
                layout = PageLayout(
                    ref="table",
                    det=(0, 0, width, height),  # 简化：整页范围
                    text=self._normalize_table_content(section),
                    order=order,
                    hash=None,
                )
            else:
                # 创建文本布局
                ref = self._determine_text_ref(section)
                layout = PageLayout(
                    ref=ref,
                    det=(0, 0, width, height),
                    text=section.strip(),
                    order=order,
                    hash=None,
                )
            
            if layout.text.strip():
                layouts.append(layout)
                order += 1
        
        return layouts

    def _split_content_sections(self, content: str) -> List[str]:
        """
        Split content into logical sections (paragraphs, tables, etc.)
        """
        # 按双换行符分段
        sections = content.split('\n\n')
        
        # 合并表格相关的段落
        merged_sections = []
        current_table = None
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            if self._looks_like_table_part(section):
                if current_table is None:
                    current_table = section
                else:
                    current_table += '\n\n' + section
            else:
                # 结束当前表格（如果有）
                if current_table:
                    merged_sections.append(current_table)
                    current_table = None
                
                # 添加非表格段落
                merged_sections.append(section)
        
        # 处理最后的表格
        if current_table:
            merged_sections.append(current_table)
        
        return merged_sections

    def _looks_like_table_part(self, text: str) -> bool:
        """
        Check if text looks like part of a table
        """
        indicators = [
            '|',  # Markdown table
            '表1', '表2', '表3', '表4', '表5',
            'Table 1', 'Table 2', 'Table 3',
            ':', '：',  # Key-value pairs
        ]
        
        for indicator in indicators:
            if indicator in text:
                return True
        
        # 检查是否有结构化数据模式
        lines = text.split('\n')
        structured_lines = 0
        for line in lines:
            line = line.strip()
            if ':' in line or '：' in line or '|' in line:
                structured_lines += 1
        
        return structured_lines >= 2

    def _is_table_section(self, text: str) -> bool:
        """
        Determine if a section contains table content
        """
        # 强表格指示符
        strong_indicators = [
            '|',  # Markdown table pipes
            '<table>', '</table>',  # HTML table tags
            '表1', '表2', '表3', '表4',
            'Table 1', 'Table 2', 'Table 3',
        ]
        
        for indicator in strong_indicators:
            if indicator in text:
                return True
        
        # 检查结构化数据密度
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if len(lines) < 3:
            return False
        
        structured_count = 0
        for line in lines:
            if ':' in line or '：' in line:
                structured_count += 1
        
        # 如果超过70%的行都是结构化数据，认为是表格
        return (structured_count / len(lines)) > 0.7

    def _normalize_table_content(self, table_text: str) -> str:
        """
        Normalize table content to HTML format for render_table_content()
        """
        # 如果已经是HTML格式，直接返回
        if '<table>' in table_text.lower() or '<tr>' in table_text.lower():
            return table_text
        
        # 如果是Markdown表格格式，转换为HTML
        if '|' in table_text and table_text.count('|') >= 4:
            return self._markdown_table_to_html(table_text)
        
        # 如果是键值对格式，转换为HTML表格
        if ':' in table_text or '：' in table_text:
            return self._key_value_to_html_table(table_text)
        
        # 其他情况，简单包装
        return f'<div class="table-content">{table_text}</div>'

    def _markdown_table_to_html(self, md_table: str) -> str:
        """
        Convert markdown table to HTML
        """
        lines = [line.strip() for line in md_table.split('\n') if line.strip()]
        html_lines = ['<table>']
        
        for i, line in enumerate(lines):
            if line.startswith('|') and line.endswith('|'):
                # 移除首尾的 |
                cells = [cell.strip() for cell in line[1:-1].split('|')]
                
                # 跳过分隔行（包含 --- 的行）
                if i == 1 and all('-' in cell for cell in cells):
                    continue
                
                # 判断是否为表头
                tag = 'th' if i == 0 else 'td'
                row_tag = 'thead' if i == 0 else 'tbody'
                
                if i == 0:
                    html_lines.append('<thead>')
                elif i == 2:  # 第一个数据行，添加tbody
                    html_lines.append('<tbody>')
                
                html_lines.append('<tr>')
                for cell in cells:
                    html_lines.append(f'<{tag}>{cell}</{tag}>')
                html_lines.append('</tr>')
                
                if i == 0:
                    html_lines.append('</thead>')
        
        if '<tbody>' in '\n'.join(html_lines):
            html_lines.append('</tbody>')
        
        html_lines.append('</table>')
        
        return '\n'.join(html_lines)

    def _key_value_to_html_table(self, kv_text: str) -> str:
        """
        Convert key-value pairs to HTML table
        """
        lines = [line.strip() for line in kv_text.split('\n') if line.strip()]
        
        html_lines = [
            '<table>',
            '<thead><tr><th>项目</th><th>值</th></tr></thead>',
            '<tbody>'
        ]
        
        for line in lines:
            # 处理中英文冒号
            if ':' in line:
                key, value = line.split(':', 1)
            elif '：' in line:
                key, value = line.split('：', 1)
            else:
                # 非键值对行，跳过或作为单列处理
                html_lines.append(f'<tr><td colspan="2">{line}</td></tr>')
                continue
            
            key = key.strip()
            value = value.strip()
            html_lines.append(f'<tr><td>{key}</td><td>{value}</td></tr>')
        
        html_lines.extend(['</tbody>', '</table>'])
        
        return '\n'.join(html_lines)

    def _determine_text_ref(self, text: str) -> str:
        """
        Determine the reference type for non-table text
        """
        text_lower = text.lower()
        
        # 检查是否为标题
        if any(indicator in text for indicator in ['#', '第', '章', 'chapter']):
            return "title"
        
        # 检查是否为图表标注
        if any(indicator in text_lower for indicator in ['图', 'figure', 'fig.', '图像']):
            return "caption"
        
        # 默认为普通文本
        return "text"

    def _render_layouts_to_markdown(
        self, 
        layouts: List[PageLayout], 
        page_num: int
    ) -> str:
        """
        Render layouts to markdown using original project's table processing
        """
        markdown_parts = [f"# Page {page_num}"]
        
        for layout in layouts:
            if layout.ref == "table" and layout.text.strip():
                # 使用原项目的表格渲染函数
                try:
                    table_markdown = render_table_content(layout.text)
                    if table_markdown.strip():
                        markdown_parts.append("")  # 空行
                        markdown_parts.append(table_markdown)
                except Exception as e:
                    # 表格渲染失败，fallback到原始文本
                    markdown_parts.append("")
                    markdown_parts.append(f"```\n{layout.text}\n```")
                    
            elif layout.ref == "title":
                markdown_parts.append("")
                markdown_parts.append(f"## {layout.text}")
                
            elif layout.ref == "caption":
                markdown_parts.append("")
                markdown_parts.append(f"*{layout.text}*")
                
            else:  # text or other
                if layout.text.strip():
                    markdown_parts.append("")
                    markdown_parts.append(layout.text)
        
        return "\n".join(markdown_parts)