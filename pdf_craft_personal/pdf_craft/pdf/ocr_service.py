from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable, Optional
from PIL import Image

from .types import Page, DeepSeekOCRSize
from ..common import AssetHub
from ..metering import AbortedCheck


@runtime_checkable
class OCRService(Protocol):
    """OCR服务抽象接口"""
    
    def image2page(
        self,
        image: Image.Image,
        page_index: int,
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        includes_footnotes: bool,
        includes_raw_image: bool,
        plot_path: "Optional[Path]",
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        device_number: Optional[int],
        aborted: AbortedCheck,
    ) -> Page:
        """将图像转换为结构化页面数据"""
        ...


class LocalOCRService:
    """本地OCR服务已移除，仅保留接口定义"""
    
    def __init__(self, page_extractor_node: "PageExtractorNode"):
        raise NotImplementedError("本地OCR服务已移除，请使用RemoteOCRService")
    
    def image2page(self, *args, **kwargs) -> Page:
        raise NotImplementedError("本地OCR服务已移除")
    
    def load_models(self) -> None:
        """本地模型加载功能已移除"""
        pass
    
    def download_models(self, revision: Optional[str]) -> None:
        """本地模型下载功能已移除"""
        pass


class RemoteOCRService:
    """远程API OCR服务实现"""
    
    def __init__(self, api_client: "AIAPIClient"):
        from ..ai_api import AIAPIClient
        self._client = api_client
    
    def image2page(
        self,
        image: Image.Image,
        page_index: int,
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        includes_footnotes: bool,
        includes_raw_image: bool,
        plot_path: "Optional[Path]",
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        device_number: Optional[int],
        aborted: AbortedCheck,
    ) -> Page:
        """使用API进行OCR识别"""
        from ..error import OCRError
        from .types import Page, PageLayout
        
        try:
            # 调用AI API进行识别
            api_response = self._client.recognize_image(
                image=image,
                max_tokens=max_tokens
            )
            
            # 提取文本内容
            text_content = self._client.extract_text_content(api_response)
            usage = self._client.get_usage_info(api_response)
            
            # 解析API响应并转换为PageLayout格式
            body_layouts = self._parse_api_response_to_layouts(
                text_content, 
                image.size,
                asset_hub,
                includes_footnotes
            )
            
            # 处理原始图像
            raw_image = image if includes_raw_image else None
            
            return Page(
                index=page_index,
                image=raw_image,
                body_layouts=body_layouts,
                footnotes_layouts=[],  # API模式暂不支持脚注分离
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
            )
            
        except Exception as e:
            raise OCRError(f"远程OCR识别失败: {e}", page_index=page_index, step_index=0)
    
    def _parse_api_response_to_layouts(
        self, 
        text_content: str, 
        image_size: tuple[int, int],
        asset_hub: AssetHub,
        includes_footnotes: bool
    ) -> list["PageLayout"]:
        """将API响应的文本解析为PageLayout列表，支持标题识别和分割"""
        from .types import PageLayout
        import re
        
        layouts = []
        
        if text_content.strip():
            # 首先尝试识别并分割标题和内容
            segments = self._split_content_with_titles(text_content)
            
            if not segments:
                segments = [text_content.strip()]
            
            # 计算每个段落的大致位置（垂直分布）
            height_per_segment = image_size[1] // max(len(segments), 1)
            
            for i, segment_info in enumerate(segments):
                if isinstance(segment_info, dict):
                    content = segment_info['content'] 
                    is_title = segment_info['is_title']
                else:
                    content = segment_info
                    is_title = False
                
                y_start = i * height_per_segment
                y_end = min((i + 1) * height_per_segment, image_size[1])
                
                # 根据是否为标题设置不同的ref
                ref = "title" if is_title else "text"
                
                layout = PageLayout(
                    ref=ref,
                    det=(0, y_start, image_size[0], y_end),
                    text=content,
                    hash=None,
                    order=i,
                )
                layouts.append(layout)
        
        return layouts
    
    def _split_content_with_titles(self, text_content: str) -> list:
        """智能分割内容，识别标题并分离"""
        import re
        
        segments = []
        lines = text_content.split('\n')
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 检测标题的模式
            is_title = self._is_title_line(line)
            
            if is_title:
                # 如果当前有累积的内容，先保存
                if current_content:
                    content_text = '\n'.join(current_content).strip()
                    if content_text:
                        segments.append({
                            'content': content_text,
                            'is_title': False
                        })
                    current_content = []
                
                # 保存标题
                segments.append({
                    'content': line,
                    'is_title': True
                })
            else:
                current_content.append(line)
        
        # 保存最后的内容
        if current_content:
            content_text = '\n'.join(current_content).strip()
            if content_text:
                segments.append({
                    'content': content_text,
                    'is_title': False
                })
        
        return segments
    
    def _is_title_line(self, line: str) -> bool:
        """判断一行文本是否为标题"""
        import re
        
        # 1. Markdown标题格式
        if re.match(r'^#+\s', line):
            return True
        
        # 2. 中文数字编号标题 (一、二、三、等)
        if re.match(r'^[一二三四五六七八九十百千万]+[、．.]', line):
            return True
        
        # 3. 阿拉伯数字编号标题 (1. 2. 1.1 等)
        if re.match(r'^\d+[\.\)]', line):
            return True
        
        # 4. 带括号的编号 ((1) (一) 等)
        if re.match(r'^\([一二三四五六七八九十\d]+\)', line):
            return True
            
        # 5. 短行且可能是标题的模式（长度较短，不含标点符号结尾）
        if (len(line) <= 20 and 
            not line.endswith(('。', '！', '？', '.', '!', '?', '，', ',', '；', ';') ) and
            any(keyword in line for keyword in ['方式', '要求', '时间', '地点', '内容', '目标', '计划', '安排', '培训', '会议', '通知', '说明'])):
            return True
        
        return False
    
    def load_models(self) -> None:
        """远程模式无需加载模型"""
        pass
    
    def download_models(self, revision: Optional[str]) -> None:
        """远程模式无需下载模型"""  
        pass