"""
按页转换PDF为Markdown的主要功能模块
每页作为独立单元处理，返回Markdown列表
"""

import sys
from os import PathLike
from pathlib import Path
from typing import List, Callable, Optional, Union

from .common import EnsureFolder
from .to_path import to_path
from .pdf import OCR, OCREvent, PDFHandler, DeepSeekOCRSize
from .metering import AbortedCheck, OCRTokensMetering
from .error import is_inline_error, to_interrupted_error
from .error import IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker
from .ai_api.config import APIConfig, load_config
from .markdown.page_render import render_page_to_markdown, load_page_from_xml


class PageTransform:
    """按页转换PDF为Markdown的转换器"""
    
    def __init__(
        self,
        models_cache_path: Union[PathLike, Optional[str]] = None,
        pdf_handler: Optional[PDFHandler] = None,
        local_only: bool = False,
        use_remote_api: bool = True,  # 强制使用远程API
        api_client: "Optional[AIAPIClient]" = None,
    ) -> None:
        self._ocr: OCR = OCR(
            model_path=models_cache_path,
            pdf_handler=pdf_handler,
            local_only=False,  # 强制禁用本地模式
            use_remote_api=True,  # 强制使用远程API
            api_client=api_client,
        )

    def transform_pages_to_markdown(
        self,
        pdf_path: Union[PathLike, str],
        pages: Optional[List[int]] = None,
        markdown_assets_path: Union[PathLike, Optional[str]] = None,
        analysing_path: Union[PathLike, Optional[str]] = None,
        ocr_size: DeepSeekOCRSize = "gundam",
        dpi: Optional[int] = None,
        max_page_image_file_size: Optional[int] = None,
        includes_cover: bool = False,
        includes_footnotes: bool = False,
        ignore_pdf_errors: IgnorePDFErrorsChecker = False,
        ignore_ocr_errors: IgnoreOCRErrorsChecker = False,
        aborted: AbortedCheck = lambda: False,
        max_ocr_tokens: Optional[int] = None,
        max_ocr_output_tokens: Optional[int] = None,
        on_ocr_event: Callable[[OCREvent], None] = lambda _: None,
        config: Optional[APIConfig] = None,
    ) -> tuple[List[str], OCRTokensMetering]:
        """将PDF按页转换为Markdown列表
        
        Args:
            pdf_path: PDF文件路径
            pages: 要处理的页码列表，例如 [1, 2, 3]，None表示处理所有页面
            markdown_assets_path: Markdown资源输出路径
            analysing_path: 临时文件路径
            ocr_size: OCR模型大小
            dpi: 图像DPI
            max_page_image_file_size: 最大页面图像文件大小
            includes_cover: 是否包含封面
            includes_footnotes: 是否包含脚注
            ignore_pdf_errors: 是否忽略PDF错误
            ignore_ocr_errors: 是否忽略OCR错误
            aborted: 中止检查函数
            max_ocr_tokens: 最大OCR输入token数
            max_ocr_output_tokens: 最大OCR输出token数
            on_ocr_event: OCR事件回调
            config: API配置
            
        Returns:
            (页面Markdown列表, OCR统计信息)
        """
        if markdown_assets_path is None:
            markdown_assets_path = Path(".") / "assets"
        else:
            markdown_assets_path = Path(markdown_assets_path)
            
        if config is None:
            try:
                config = load_config()
            except ValueError:
                # 如果配置加载失败，使用默认配置
                config = APIConfig(
                    base_url="https://api.example.com",
                    api_key="",
                    default_model="",
                )

        try:
            # 使用临时文件处理
            with EnsureFolder(
                path=to_path(analysing_path) if analysing_path is not None else None,
            ) as analysing_path:
                    assets_path, pages_path, cover_path, metering = self._extract_pages_from_pdf(
                        pdf_path=Path(pdf_path),
                        pages=pages,
                        analysing_path=analysing_path,
                        ocr_size=ocr_size,
                        dpi=dpi,
                        max_page_image_file_size=max_page_image_file_size,
                        includes_cover=includes_cover,
                        includes_footnotes=includes_footnotes,
                        ignore_pdf_errors=ignore_pdf_errors,
                        ignore_ocr_errors=ignore_ocr_errors,
                        aborted=aborted,
                        max_tokens=max_ocr_tokens,
                        max_output_tokens=max_ocr_output_tokens,
                        on_ocr_event=on_ocr_event,
                        use_concurrent=False,
                        max_workers=1,
                        batch_size=1,
                    )
                    
                    page_markdowns = self._render_pages_to_markdown(
                        pages_path=pages_path,
                        assets_path=assets_path,
                        output_assets_path=markdown_assets_path,
                        config=config,
                    )
                    
                    return page_markdowns, metering

        except Exception as raw_error:
            error = to_interrupted_error(raw_error)
            if error:
                raise error from raw_error
            elif is_inline_error(raw_error):
                raise
            else:
                raise RuntimeError(f"transform {pdf_path} to page markdowns failed") from raw_error

    def _extract_pages_from_pdf(
        self,
        pdf_path: Path,
        pages: Optional[List[int]],
        analysing_path: Path,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_cover: bool,
        includes_footnotes: bool,
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        aborted: AbortedCheck,
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        use_concurrent: bool,
        max_workers: int,
        batch_size: int,
        on_ocr_event: Callable[[OCREvent], None],
    ):
        """从PDF提取页面数据"""
        assets_path = analysing_path / "assets"
        pages_path = analysing_path / "ocr"

        cover_path: Optional[Path] = None
        if includes_cover:
            cover_path = analysing_path / "cover.png"

        # 选择处理方式：并发还是顺序
        if use_concurrent and self._ocr._use_remote_api:
            # 使用并发处理器
            from .concurrent_processor import ConcurrentPDFProcessor
            
            processor = ConcurrentPDFProcessor(
                ocr=self._ocr,
                max_workers=max_workers,
                batch_size=batch_size,
            )
            
            metering = processor.process_pdf_concurrent(
                pdf_path=pdf_path,
                asset_path=assets_path,
                ocr_path=pages_path,
                ocr_size=ocr_size,
                dpi=dpi,
                max_page_image_file_size=max_page_image_file_size,
                includes_footnotes=includes_footnotes,
                ignore_pdf_errors=ignore_pdf_errors,
                ignore_ocr_errors=ignore_ocr_errors,
                plot_path=None,  # 页面级处理不需要plot
                cover_path=cover_path,
                aborted=aborted,
                page_indexes=pages if pages else range(1, sys.maxsize),
                max_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                on_ocr_event=on_ocr_event,
            )
        else:
            # 使用原有的顺序处理
            metering = OCRTokensMetering(
                input_tokens=0,
                output_tokens=0,
            )
            for event in self._ocr.recognize(
                pdf_path=pdf_path,
                asset_path=assets_path,
                ocr_path=pages_path,
                ocr_size=ocr_size,
                dpi=dpi,
                max_page_image_file_size=max_page_image_file_size,
                includes_footnotes=includes_footnotes,
                ignore_pdf_errors=ignore_pdf_errors,
                ignore_ocr_errors=ignore_ocr_errors,
                plot_path=None,  # 页面级处理不需要plot
                cover_path=cover_path,
                aborted=aborted,
                page_indexes=pages if pages else range(1, sys.maxsize),
                max_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
            ):
                on_ocr_event(event)
                metering.input_tokens += event.input_tokens
                metering.output_tokens += event.output_tokens

        if cover_path and not cover_path.exists():
            cover_path = None

        return assets_path, pages_path, cover_path, metering

    def _render_pages_to_markdown(
        self,
        pages_path: Path,
        assets_path: Path,
        output_assets_path: Path,
        config: APIConfig,
    ) -> List[str]:
        """将页面XML文件渲染为Markdown列表"""
        page_markdowns: List[str] = []
        
        # 确保输出目录存在
        output_assets_path.mkdir(parents=True, exist_ok=True)
        
        # 获取所有页面XML文件并排序
        page_files = sorted(
            pages_path.glob("page_*.xml"),
            key=lambda x: int(x.stem.split("_")[1])
        )
        
        for page_file in page_files:
            try:
                # 加载页面
                page = load_page_from_xml(page_file)
                
                # 设置资源引用路径（相对于markdown文件的位置）
                asset_ref_path = Path("assets")
                
                # 渲染页面为Markdown
                markdown_content = render_page_to_markdown(
                    page=page,
                    assets_path=assets_path,
                    output_assets_path=output_assets_path,
                    asset_ref_path=asset_ref_path,
                    config=config,
                )
                
                page_markdowns.append(markdown_content)
                
            except Exception as e:
                print(f"Warning: Failed to render page {page_file.name}: {e}")
                # 添加空白页面或错误信息
                page_markdowns.append(f"<!-- Page {page_file.stem} failed to render: {e} -->")
        
        return page_markdowns