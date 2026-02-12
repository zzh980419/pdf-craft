"""
批量OCR服务

支持真正的批量API调用，一次请求处理多页
"""

import re
from typing import List, Dict, Any, Optional
from PIL import Image

from .types import Page, PageLayout, DeepSeekOCRSize
from ..common import AssetHub
from ..metering import AbortedCheck
from ..error import OCRError


class BatchOCRService:
    """批量OCR服务 - 使用模型的批量推理功能"""
    
    def __init__(self, api_client):
        from ..ai_api.client_optimized import OptimizedAIAPIClient
        self._client = api_client
        
    def process_pages_batch(
        self,
        pages_data: List[Dict],  # [{'image': image, 'page_index': int, 'asset_hub': AssetHub, ...}, ...]
        ocr_size: DeepSeekOCRSize,
        includes_footnotes: bool,
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        aborted: AbortedCheck,
    ) -> List[Page]:
        """批量处理多个页面"""
        
        if not pages_data:
            return []
            
        # 提取图像
        images = [page_data['image'] for page_data in pages_data]
        
        try:
            # 使用批量API
            api_response = self._client.recognize_images_batch_api(
                images=images,
                max_tokens=max_tokens
            )
            
            # 解析批量响应
            return self._parse_batch_response(api_response, pages_data, includes_footnotes)
            
        except Exception as e:
            # 如果批量失败，回退到单个处理
            print(f"批量处理失败，回退到单个处理: {e}")
            return self._fallback_to_individual(pages_data, ocr_size, includes_footnotes, 
                                               max_tokens, max_output_tokens, aborted)
    
    def _parse_batch_response(
        self, 
        api_response: Dict[str, Any], 
        pages_data: List[Dict],
        includes_footnotes: bool
    ) -> List[Page]:
        """解析批量API响应"""
        
        # 提取完整文本
        text_content = self._client.extract_text_content(api_response)
        usage = self._client.get_usage_info(api_response)
        
        # 按页面分割内容
        page_contents = self._split_batch_content(text_content, len(pages_data))
        
        # 为每个页面创建Page对象
        pages = []
        total_input_tokens = usage.get('input_tokens', 0)
        total_output_tokens = usage.get('output_tokens', 0)
        
        # 平均分配token使用（简单估算）
        avg_input_tokens = total_input_tokens // len(pages_data) if pages_data else 0
        avg_output_tokens = total_output_tokens // len(pages_data) if pages_data else 0
        
        for i, page_data in enumerate(pages_data):
            page_content = page_contents[i] if i < len(page_contents) else ""
            
            # 解析页面内容为布局
            body_layouts = self._parse_page_content_to_layouts(
                page_content,
                page_data['image'].size,
                page_data['asset_hub'],
                includes_footnotes
            )
            
            # 处理原始图像
            raw_image = page_data['image'] if page_data.get('includes_raw_image', False) else None
            
            page = Page(
                index=page_data['page_index'],
                image=raw_image,
                body_layouts=body_layouts,
                footnotes_layouts=[],  # 批量模式暂不处理脚注
                input_tokens=avg_input_tokens,
                output_tokens=avg_output_tokens,
            )
            
            pages.append(page)
        
        return pages
    
    def _split_batch_content(self, text_content: str, num_pages: int) -> List[str]:
        """将批量响应按页面分割"""
        
        # 查找页面分隔符
        page_pattern = r'===\s*PAGE\s*(\d+)\s*==='
        parts = re.split(page_pattern, text_content, flags=re.IGNORECASE)
        
        page_contents = []
        
        if len(parts) > 1:
            # 有分隔符的情况
            i = 1
            while i < len(parts):
                if i + 1 < len(parts):
                    page_contents.append(parts[i + 1].strip())
                i += 2
        else:
            # 没有分隔符，尝试平均分割
            lines = text_content.split('\n')
            lines_per_page = max(1, len(lines) // num_pages)
            
            for i in range(num_pages):
                start_idx = i * lines_per_page
                end_idx = start_idx + lines_per_page if i < num_pages - 1 else len(lines)
                page_content = '\n'.join(lines[start_idx:end_idx])
                page_contents.append(page_content.strip())
        
        # 确保有足够的页面内容
        while len(page_contents) < num_pages:
            page_contents.append("")
        
        return page_contents[:num_pages]
    
    def _parse_page_content_to_layouts(
        self,
        content: str,
        image_size: tuple,
        asset_hub: AssetHub,
        includes_footnotes: bool
    ) -> List[PageLayout]:
        """将页面内容解析为布局列表"""
        
        if not content.strip():
            return []
        
        # 简单的布局解析 - 将整个内容作为一个文本布局
        # 在实际使用中，这里可以做更复杂的内容分割和分类
        
        layout = PageLayout(
            ref="text",  # 批量模式下统一标记为text
            det=(0, 0, image_size[0], image_size[1]),  # 整个图像区域
            text=content,
            order=0,
            hash=None
        )
        
        return [layout]
    
    def _fallback_to_individual(
        self,
        pages_data: List[Dict],
        ocr_size: DeepSeekOCRSize,
        includes_footnotes: bool,
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        aborted: AbortedCheck,
    ) -> List[Page]:
        """回退到单个页面处理"""
        
        from .ocr_service import RemoteOCRService
        
        # 创建单页OCR服务
        individual_service = RemoteOCRService(self._client)
        
        pages = []
        for page_data in pages_data:
            try:
                page = individual_service.image2page(
                    image=page_data['image'],
                    page_index=page_data['page_index'],
                    asset_hub=page_data['asset_hub'],
                    ocr_size=ocr_size,
                    includes_footnotes=includes_footnotes,
                    includes_raw_image=page_data.get('includes_raw_image', False),
                    plot_path=page_data.get('plot_path'),
                    max_tokens=max_tokens,
                    max_output_tokens=max_output_tokens,
                    device_number=None,
                    aborted=aborted,
                )
                pages.append(page)
                
            except Exception as e:
                # 创建错误页面
                error_page = Page(
                    index=page_data['page_index'],
                    image=None,
                    body_layouts=[PageLayout(
                        ref="text",
                        det=(0, 0, page_data['image'].size[0], page_data['image'].size[1]),
                        text=f"[[Page {page_data['page_index']} processing failed: {e}]]",
                        order=0,
                        hash=None
                    )],
                    footnotes_layouts=[],
                    input_tokens=0,
                    output_tokens=0,
                )
                pages.append(error_page)
        
        return pages