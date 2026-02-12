from dataclasses import dataclass
import sys
import time

from typing import Container, Generator, TypeVar, Callable, Optional, Union
from threading import Lock
from enum import auto, Enum
from pathlib import Path
from os import PathLike

from ..common import save_xml, AssetHub
from ..to_path import to_path
from ..error import PDFError, OCRError, IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker
from ..metering import check_aborted, AbortedCheck
from .page_extractor import Page, PageLayout, PageExtractorNode
from .page_ref import PageRefContext
from .types import encode, DeepSeekOCRSize, PDFDocumentMetadata
from .handler import PDFHandler, DefaultPDFHandler
from .ocr_service import OCRService, RemoteOCRService



class OCREventKind(Enum):
    START = auto()
    IGNORE = auto()
    SKIP = auto()
    RENDERED = auto()
    COMPLETE = auto()
    FAILED = auto()

@dataclass
class OCREvent:
    kind: OCREventKind
    page_index: int
    total_pages: int
    cost_time_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[Exception] = None

class OCR:
    def __init__(
            self,
            model_path: Union[PathLike, Optional[str]],
            pdf_handler: Optional[PDFHandler],
            local_only: bool,
            use_remote_api: bool = True,
            api_client: "Optional[AIAPIClient]" = None,
        ) -> None:
        self._pdf_handler = pdf_handler
        self._pdf_handler_lock = Lock()
        self._use_remote_api = use_remote_api
        
        if use_remote_api:
            if api_client is None:
                from ..ai_api import AIAPIClient, load_config
                config = load_config()
                api_client = AIAPIClient(config)
            self._ocr_service: OCRService = RemoteOCRService(api_client)
            
            # 尝试使用优化的API客户端和批量服务
            try:
                from ..ai_api.client_optimized import OptimizedAIAPIClient
                from .batch_ocr_service import BatchOCRService
                
                # 如果是标准API客户端，升级到优化版
                if type(api_client).__name__ == 'AIAPIClient':
                    optimized_client = OptimizedAIAPIClient(api_client.config)
                    self._batch_service = BatchOCRService(optimized_client)
                elif hasattr(api_client, 'recognize_images_batch_api'):
                    self._batch_service = BatchOCRService(api_client)
                else:
                    self._batch_service = None
            except ImportError:
                self._batch_service = None
        else:
            # 本地模式已移除，强制使用远程API
            raise ValueError("本地模型功能已移除，请使用 use_remote_api=True")

    def predownload(self, revision: Optional[str]) -> None:
        """本地模型下载功能已移除"""
        pass

    def load_models(self) -> None:
        """本地模型加载功能已移除"""
        pass

    def metadata(self, pdf_path: Path) -> PDFDocumentMetadata:
        document = self._get_pdf_handler().open(pdf_path)
        try:
            return document.metadata()
        finally:
            document.close()

    def recognize(
            self,
            pdf_path: Path,
            asset_path: Path,
            ocr_path: Path,
            ocr_size: DeepSeekOCRSize = "gundam",
            dpi: Optional[int] = None,
            max_page_image_file_size: Optional[int] = None,
            includes_footnotes: bool = False,
            ignore_pdf_errors: IgnorePDFErrorsChecker = False,
            ignore_ocr_errors: IgnoreOCRErrorsChecker = False,
            plot_path: Optional[Path] = None,
            cover_path: Optional[Path] = None,
            aborted: AbortedCheck = lambda: False,
            page_indexes: Container[int] = range(1, sys.maxsize),
            max_tokens: Optional[int] = None,
            max_output_tokens: Optional[int] = None,
            device_number: Optional[int] = None,
        ) -> Generator[OCREvent, None, None]:

        ocr_path.mkdir(parents=True, exist_ok=True)
        if plot_path is not None:
            plot_path.mkdir(parents=True, exist_ok=True)

        done_path = ocr_path / "done"
        did_ignore_any: bool = False
        if done_path.exists():
            return

        remain_tokens: Optional[int] = max_tokens
        remain_output_tokens: Optional[int] = max_output_tokens

        with PageRefContext(
            pdf_path=pdf_path,
            pdf_handler=self._get_pdf_handler(),
        ) as refs:

            pages_count = refs.pages_count
            asset_hub = AssetHub(asset_path)

            for ref in refs:
                check_aborted(aborted)
                start_time = time.perf_counter()
                yield OCREvent(
                    kind=OCREventKind.START,
                    page_index=ref.page_index,
                    total_pages=pages_count,
                )
                if ref.page_index not in page_indexes:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    did_ignore_any = True
                    yield OCREvent(
                        kind=OCREventKind.IGNORE,
                        page_index=ref.page_index,
                        total_pages=pages_count,
                        cost_time_ms=elapsed_ms,
                    )
                    continue

                filename = f"page_{ref.page_index}.xml"
                file_path = ocr_path / filename

                if file_path.exists():
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    yield OCREvent(
                        kind=OCREventKind.SKIP,
                        page_index=ref.page_index,
                        total_pages=pages_count,
                        cost_time_ms=elapsed_ms,
                    )
                else:
                    # TokenLimitError for API usage (replaced doc-page-extractor import)
                    class TokenLimitError(Exception):
                        pass
                    
                    if remain_tokens is not None and remain_tokens <= 0:
                        raise TokenLimitError()
                    if remain_output_tokens is not None and remain_output_tokens <= 0:
                        raise TokenLimitError()

                    page: Optional[Page] = None
                    recognized_error: Optional[Exception] = None

                    try:
                        image = ref.render(
                            dpi=dpi if dpi is not None else 300, # DPI=300 for scanned page
                            max_image_file_size=max_page_image_file_size,
                        )
                        yield OCREvent(
                            kind=OCREventKind.RENDERED,
                            page_index=ref.page_index,
                            total_pages=pages_count,
                            cost_time_ms=int((time.perf_counter() - start_time) * 1000),
                            input_tokens=0,
                            output_tokens=0,
                        )
                        
                        page = self._ocr_service.image2page(
                            image=image,
                            page_index=ref.page_index,
                            asset_hub=asset_hub,
                            ocr_size=ocr_size,
                            includes_footnotes=includes_footnotes,
                            includes_raw_image=(ref.page_index == 1),
                            plot_path=plot_path,
                            max_tokens=remain_tokens,
                            max_output_tokens=remain_output_tokens,
                            device_number=device_number,
                            aborted=aborted,
                        )
                    except PDFError as error:
                        if not _check_ignore_error(ignore_pdf_errors, error):
                            raise
                        recognized_error = error

                    except OCRError as error:
                        if not _check_ignore_error(ignore_ocr_errors, error):
                            raise
                        recognized_error = error

                    if page is None:
                        page = self._create_warn_page(
                            page_index=ref.page_index,
                            text=f"[[Page {ref.page_index} extraction failed due to PDF rendering error]]",
                        )

                    save_xml(encode(page), file_path)

                    if cover_path and page.image:
                        cover_path.parent.mkdir(parents=True, exist_ok=True)
                        page.image.save(cover_path, format="PNG")

                    yield OCREvent(
                        kind=OCREventKind.COMPLETE if recognized_error is None else OCREventKind.FAILED,
                        error=recognized_error,
                        page_index=ref.page_index,
                        total_pages=pages_count,
                        cost_time_ms=int((time.perf_counter() - start_time) * 1000),
                        input_tokens=page.input_tokens,
                        output_tokens=page.output_tokens,
                    )
                    if remain_tokens is not None:
                        remain_tokens -= page.input_tokens
                        remain_tokens -= page.output_tokens

                    if remain_output_tokens is not None:
                        remain_output_tokens -= page.output_tokens

        if not did_ignore_any:
            done_path.touch()

    def _get_pdf_handler(self) -> PDFHandler:
        if self._pdf_handler is not None:
            return self._pdf_handler

        with self._pdf_handler_lock:
            if self._pdf_handler is None:
                self._pdf_handler = DefaultPDFHandler()
            return self._pdf_handler

    def _create_warn_page(self, page_index: int, text: str) -> Page:
        page = Page(
            index=page_index,
            image=None,
            body_layouts=[],
            footnotes_layouts=[],
            input_tokens=0,
            output_tokens=0,
        )
        page.body_layouts.append(PageLayout(
            ref="text",
            det=(0, 0, 100, 100),
            text=text,
            hash=None,
            order=0,
        ))
        return page

_T =  TypeVar("_T", bound=Exception)

def _check_ignore_error(check: Union[bool, Callable[[_T], bool]], error: _T) -> bool:
    if isinstance(check, bool):
        return check
    else:
        return check(error)
