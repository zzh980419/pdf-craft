from os import PathLike
from pathlib import Path
from typing import Callable, Optional, Union

from .common import remove_surrogates, EnsureFolder
from .error import PDFError
from .to_path import to_path
from .pdf import OCR, OCREvent, PDFHandler, DeepSeekOCRSize
from .sequence import generate_chapter_files
from .toc import analyse_toc
from .error import is_inline_error, to_interrupted_error
from .metering import AbortedCheck, OCRTokensMetering
from .markdown.render import render_markdown_file
from .error import IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker


class Transform:
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
    def transform_markdown(
        self,
        pdf_path: Union[PathLike, str],
        markdown_path: Union[PathLike, str],
        markdown_assets_path: Union[PathLike, Optional[str]] = None,
        analysing_path: Union[PathLike, Optional[str]] = None,
        ocr_size: DeepSeekOCRSize = "gundam",
        dpi: Optional[int] = None,
        max_page_image_file_size: Optional[int] = None,
        includes_cover: bool = False,
        includes_footnotes: bool = False,
        generate_plot: bool = False,
        toc_assumed: bool = False,
        ignore_pdf_errors: IgnorePDFErrorsChecker = False,
        ignore_ocr_errors: IgnoreOCRErrorsChecker = False,
        aborted: AbortedCheck = lambda: False,
        max_ocr_tokens: Optional[int] = None,
        max_ocr_output_tokens: Optional[int] = None,
        on_ocr_event: Callable[[OCREvent], None] = lambda _: None,
    ) -> OCRTokensMetering: # pyright: ignore[reportReturnType]

        if markdown_assets_path is None:
            markdown_assets_path = Path(".") / "assets"
        else:
            markdown_assets_path = Path(markdown_assets_path)
        try:
            # 使用EnsureFolder自动清理临时文件
            with EnsureFolder(
                path=to_path(analysing_path) if analysing_path is not None else None,
            ) as analysing_path:
                    asserts_path, chapters_path, toc_path, cover_path, metering = self._extract_from_pdf(
                        pdf_path=Path(pdf_path),
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
                        max_tokens=max_ocr_tokens,
                        max_output_tokens=max_ocr_output_tokens,
                        on_ocr_event=on_ocr_event,
                    )
                    render_markdown_file(
                        chapters_path=chapters_path,
                        assets_path=asserts_path,
                        output_path=Path(markdown_path),
                        output_assets_path=markdown_assets_path,
                        cover_path=cover_path,
                        aborted=aborted,
                    )
                    return metering

        except Exception as raw_error:
            error = to_interrupted_error(raw_error)
            if error:
                raise error from raw_error
            elif is_inline_error(raw_error):
                raise
            else:
                raise RuntimeError(f"transform {pdf_path} to markdown failed") from raw_error

    def _extract_from_pdf(
        self,
        pdf_path: Path,
        analysing_path: Path,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_cover: bool,
        includes_footnotes: bool,
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        generate_plot: bool,
        toc_assumed: bool,
        aborted: AbortedCheck,
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        on_ocr_event: Callable[[OCREvent], None],
    ):

        asserts_path = analysing_path / "assets"
        pages_path = analysing_path / "ocr"
        chapters_path = analysing_path / "chapters"
        toc_path = analysing_path / "toc.xml"

        cover_path: Optional[Path] = None
        plot_path: Optional[Path] = None
        if includes_cover:
            cover_path = analysing_path / "cover.png"
        if generate_plot:
            plot_path = analysing_path / "plots"

        # 使用顺序处理（简化版本，不支持并发）
        metering = OCRTokensMetering(
            input_tokens=0,
            output_tokens=0,
        )
        for event in self._ocr.recognize(
            pdf_path=pdf_path,
            asset_path=asserts_path,
            ocr_path=pages_path,
            ocr_size=ocr_size,
            dpi=dpi,
            max_page_image_file_size=max_page_image_file_size,
            includes_footnotes=includes_footnotes,
            ignore_pdf_errors=ignore_pdf_errors,
            ignore_ocr_errors=ignore_ocr_errors,
            plot_path=plot_path,
            cover_path=cover_path,
            aborted=aborted,
            max_tokens=max_tokens,
            max_output_tokens=max_output_tokens,
        ):
            on_ocr_event(event)
            metering.input_tokens += event.input_tokens
            metering.output_tokens += event.output_tokens

        toc = analyse_toc(
            pages_path=pages_path,
            toc_path=toc_path,
            toc_assumed=toc_assumed,
        )
        generate_chapter_files(
            pages_path=pages_path,
            chapters_path=chapters_path,
            toc=toc,
        )
        if cover_path and not cover_path.exists():
            cover_path = None

        return asserts_path, chapters_path, toc_path, cover_path, metering

    def _normalize_text_in_meta(self, text: Optional[str]) -> Optional[str]:
        if text is None:
            return None
        return remove_surrogates(text)
