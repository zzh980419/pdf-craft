from .pdf import (
    pdf_pages_count,
    DeepSeekOCRSize,
    PDFDocument,
    PDFHandler,
    PDFDocumentMetadata,
    DefaultPDFHandler,
    DefaultPDFDocument,
    OCREvent,
    OCREventKind,
)

from .transform import Transform, OCRTokensMetering
from .error import InterruptedError, PDFError, OCRError, IgnoreOCRErrorsChecker, IgnorePDFErrorsChecker
from .metering import AbortedCheck, InterruptedKind
from .functions import transform_markdown, transform_pages_markdown

# EPUB相关功能已移除，仅保留接口兼容性
class BookMeta:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("EPUB功能已移除")

class TableRender:
    HTML = "html"

class LaTeXRender:
    MATHML = "mathml"
