import os
from os import PathLike
from typing import Callable, List, Tuple, Optional, Union

from .pdf import OCREvent, PDFHandler, DeepSeekOCRSize
from .transform import Transform
from .page_transform import PageTransform
from .metering import AbortedCheck, OCRTokensMetering
from .error import IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker
from .ai_api.config import get_env_bool, load_config


def transform_markdown(
    pdf_path: Union[PathLike, str],
    markdown_path: Union[PathLike, str],
    pdf_handler: Optional[PDFHandler] = None,
    markdown_assets_path: Union[PathLike, Optional[str]] = None,
    analysing_path: Union[PathLike, Optional[str]] = None,
    ocr_size: DeepSeekOCRSize = "gundam",
    models_cache_path: Union[PathLike, Optional[str]] = None,
    local_only: bool = False,
    use_remote_api: bool = True,
    api_client: "Optional[AIAPIClient]" = None,
    dpi: Optional[int] = None,
    max_page_image_file_size: Optional[int] = None,
    includes_cover: bool = False,
    includes_footnotes: bool = False,
    ignore_pdf_errors: IgnorePDFErrorsChecker = False,
    ignore_ocr_errors: IgnoreOCRErrorsChecker = False,
    generate_plot: bool = False,
    toc_assumed: bool = False,
    aborted: AbortedCheck = lambda: False,
    max_ocr_tokens: Optional[int] = None,
    max_ocr_output_tokens: Optional[int] = None,
    on_ocr_event: Callable[[OCREvent], None] = lambda _: None,
) -> OCRTokensMetering:

    return Transform(
        models_cache_path=models_cache_path,
        pdf_handler=pdf_handler,
        local_only=False,  # 强制禁用本地模式
        use_remote_api=True,  # 强制使用远程API
        api_client=api_client,
    ).transform_markdown(
        pdf_path=pdf_path,
        markdown_path=markdown_path,
        markdown_assets_path=markdown_assets_path,
        analysing_path=analysing_path,
        ocr_size=ocr_size,
        dpi=dpi,
        max_page_image_file_size=max_page_image_file_size,
        includes_cover=includes_cover,
        includes_footnotes=includes_footnotes,
        ignore_pdf_errors=ignore_pdf_errors,
        ignore_ocr_errors=ignore_ocr_errors,
        generate_plot=generate_plot,
        toc_assumed=toc_assumed,
        aborted=aborted,
        max_ocr_tokens=max_ocr_tokens,
        max_ocr_output_tokens=max_ocr_output_tokens,
        on_ocr_event=on_ocr_event,
    )


def transform_pages_markdown(
    pdf_path: Union[PathLike, str],
    pages: Optional[List[int]] = None,
    pdf_handler: Optional[PDFHandler] = None,
    markdown_assets_path: Union[PathLike, Optional[str]] = None,
    analysing_path: Union[PathLike, Optional[str]] = None,
    ocr_size: DeepSeekOCRSize = "gundam",
    models_cache_path: Union[PathLike, Optional[str]] = None,
    local_only: bool = False,
    use_remote_api: bool = True,
    api_client: "Optional[AIAPIClient]" = None,
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
) -> Tuple[List[str], OCRTokensMetering]:
    """按页转换PDF为Markdown列表
    
    将PDF文件按页解析，每页作为独立单元处理，返回Markdown字符串列表。
    
    Args:
        pdf_path: PDF文件路径
        pages: 要处理的页码列表，例如 [1, 2, 3]，None表示处理所有页面
        pdf_handler: PDF处理器（可选）
        markdown_assets_path: Markdown资源输出路径
        analysing_path: 临时文件分析路径
        ocr_size: OCR模型大小 ("tiny", "small", "base", "large", "gundam")
        models_cache_path: 模型缓存路径
        local_only: 是否仅使用本地模型
        use_remote_api: 是否使用远程API
        api_client: API客户端（可选）
        dpi: 图像DPI设置
        max_page_image_file_size: 最大页面图像文件大小
        includes_cover: 是否包含封面
        includes_footnotes: 是否包含脚注
        ignore_pdf_errors: 是否忽略PDF错误
        ignore_ocr_errors: 是否忽略OCR错误
        aborted: 中止检查函数
        max_ocr_tokens: 最大OCR输入token数
        max_ocr_output_tokens: 最大OCR输出token数
        on_ocr_event: OCR事件回调函数
        
    Returns:
        Tuple[List[str], OCRTokensMetering]: (页面Markdown列表, OCR统计信息)
        
    Example:
        >>> page_markdowns, metering = transform_pages_markdown(
        ...     pdf_path="document.pdf",
        ...     use_remote_api=True
        ... )
        >>> print(f"转换了 {len(page_markdowns)} 页")
        >>> print(f"第一页内容: {page_markdowns[0][:100]}...")
    """
    
    return PageTransform(
        models_cache_path=models_cache_path,
        pdf_handler=pdf_handler,
        local_only=False,  # 强制禁用本地模式
        use_remote_api=True,  # 强制使用远程API
        api_client=api_client,
    ).transform_pages_to_markdown(
        pdf_path=pdf_path,
        pages=pages,
        markdown_assets_path=markdown_assets_path,
        analysing_path=analysing_path,
        ocr_size=ocr_size,
        dpi=dpi,
        max_page_image_file_size=max_page_image_file_size,
        includes_cover=includes_cover,
        includes_footnotes=includes_footnotes,
        ignore_pdf_errors=ignore_pdf_errors,
        ignore_ocr_errors=ignore_ocr_errors,
        aborted=aborted,
        max_ocr_tokens=max_ocr_tokens,
        max_ocr_output_tokens=max_ocr_output_tokens,
        on_ocr_event=on_ocr_event,
        config=load_config(),
    )
