"""
Remote OCR that replaces local model calls with remote API calls
"""

import sys
import time
from os import PathLike
from pathlib import Path
from threading import Lock
from typing import Container, Generator

from PIL.Image import Image

from ..common import AssetHub, save_xml
from ..error import IgnoreOCRErrorsChecker, IgnorePDFErrorsChecker, OCRError, PDFError
from ..metering import AbortedCheck, check_aborted
from ..pdf.handler import DefaultPDFHandler, PDFHandler
from ..pdf.ocr import OCREvent, OCREventKind
from ..pdf.page_ref import PageRefContext
from ..pdf.types import DeepSeekOCRSize, PDFDocumentMetadata, encode
from ..to_path import to_path
from .remote_extractor import RemotePageExtractorNode


class RemoteOCR:
    """
    Remote OCR that uses remote API instead of local models
    Compatible interface with original OCR class
    """
    
    def __init__(
        self,
        model_path: PathLike | str | None,
        pdf_handler: PDFHandler | None,
        local_only: bool,
    ) -> None:
        self._pdf_handler = pdf_handler
        self._pdf_handler_lock = Lock()
        
        # Use remote extractor instead of local one
        self._extractor = RemotePageExtractorNode(
            model_path=to_path(model_path) if model_path is not None else None,
            local_only=local_only,
        )

    def predownload(self, revision: str | None) -> None:
        """No-op for remote API"""
        self._extractor.download_models(revision)

    def load_models(self) -> None:
        """No-op for remote API"""
        self._extractor.load_models()

    def metadata(self, pdf_path: Path) -> PDFDocumentMetadata:
        """Get PDF metadata (unchanged from original)"""
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
        dpi: int | None = None,
        max_page_image_file_size: int | None = None,
        includes_footnotes: bool = False,
        ignore_pdf_errors: IgnorePDFErrorsChecker = False,
        ignore_ocr_errors: IgnoreOCRErrorsChecker = False,
        plot_path: Path | None = None,
        cover_path: Path | None = None,
        aborted: AbortedCheck = lambda: False,
        page_indexes: Container[int] = range(1, sys.maxsize),
        max_tokens: int | None = None,
        max_output_tokens: int | None = None,
        device_number: int | None = None,
    ) -> Generator[OCREvent, None, None]:
        """
        OCR recognition using remote API
        (Same interface as original OCR.recognize)
        """
        ocr_path.mkdir(parents=True, exist_ok=True)
        if plot_path is not None:
            plot_path.mkdir(parents=True, exist_ok=True)

        done_path = ocr_path / "done"
        did_ignore_any: bool = False
        if done_path.exists():
            return

        remain_tokens: int | None = max_tokens
        remain_output_tokens: int | None = max_output_tokens

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
                    # Check token limits
                    if remain_tokens is not None and remain_tokens <= 0:
                        from doc_page_extractor import TokenLimitError
                        raise TokenLimitError()
                    if remain_output_tokens is not None and remain_output_tokens <= 0:
                        from doc_page_extractor import TokenLimitError
                        raise TokenLimitError()

                    page = None
                    image: Image | None = None
                    recognized_error: Exception | None = None

                    try:
                        image = ref.render(
                            dpi=dpi if dpi is not None else 300,
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
                        
                        # Use remote extractor instead of local one
                        page = self._extractor.image2page(
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
                        page = self._create_fallback_page(
                            asset_hub=asset_hub,
                            page_index=ref.page_index,
                            image=image,
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
        """Get PDF handler (unchanged from original)"""
        if self._pdf_handler is not None:
            return self._pdf_handler

        with self._pdf_handler_lock:
            if self._pdf_handler is None:
                self._pdf_handler = DefaultPDFHandler()
            return self._pdf_handler

    def _create_fallback_page(self, asset_hub: AssetHub, page_index: int, image: Image | None):
        """Create fallback page (unchanged from original)"""
        from ..pdf.page_extractor import PageLayout
        from ..pdf.types import Page
        
        layout: PageLayout
        if image is not None:
            width, height = image.size
            full_page_det = (0, 0, width, height)
            image_hash = asset_hub.clip(image, full_page_det)
            layout = PageLayout(
                ref="image",
                det=full_page_det,
                text="",
                hash=image_hash,
                order=0,
            )
        else:
            layout = PageLayout(
                ref="text",
                det=(0, 0, 100, 100),
                text=f"[[Page {page_index} extraction failed due to PDF rendering error]]",
                hash=None,
                order=0,
            )
        return Page(
            index=page_index,
            image=image,
            body_layouts=[layout],
            footnotes_layouts=[],
            input_tokens=0,
            output_tokens=0,
        )


def _check_ignore_error(check, error):
    """Check if error should be ignored (unchanged from original)"""
    if isinstance(check, bool):
        return check
    else:
        return check(error)