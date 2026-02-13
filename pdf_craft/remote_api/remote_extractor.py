"""
Remote Page Extractor that replaces local model calls with remote API calls
"""

import re
import tempfile
from pathlib import Path
from typing import Iterable, List

from PIL.Image import Image

from ..common import ASSET_TAGS, AssetHub, remove_surrogates
from ..error import OCRError
from ..metering import AbortedCheck, check_aborted
from ..pdf.types import DeepSeekOCRSize, Page, PageLayout
from .client import AIAPIClient
from .config import load_config


class RemotePageExtractorNode:
    """
    Remote page extractor that uses remote API instead of local models
    Compatible interface with original PageExtractorNode
    """
    
    def __init__(
        self,
        model_path: Path | None = None,
        local_only: bool = False,
        enable_devices_numbers: Iterable[int] | None = None,
        api_client: AIAPIClient | None = None,
    ) -> None:
        # Initialize remote API client
        if api_client is None:
            config = load_config()
            api_client = AIAPIClient(config)
        self._api_client = api_client
        
        # Store parameters for compatibility (not used in remote mode)
        self._model_path = model_path
        self._local_only = local_only
        self._enable_devices_numbers = enable_devices_numbers

    def download_models(self, revision: str | None) -> None:
        """No-op for remote API (models are already deployed)"""
        pass

    def load_models(self) -> None:
        """No-op for remote API (models are already loaded remotely)"""
        pass

    def image2page(
        self,
        image: Image,
        page_index: int,
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        includes_footnotes: bool,
        includes_raw_image: bool,
        plot_path: Path | None,
        max_tokens: int | None,
        max_output_tokens: int | None,
        device_number: int | None,
        aborted: AbortedCheck,
    ) -> Page:
        """
        Extract page content using remote API
        """
        body_layouts: List[PageLayout] = []
        footnotes_layouts: List[PageLayout] = []
        raw_image: Image | None = None
        
        input_tokens = 0
        output_tokens = 0

        if includes_raw_image:
            raw_image = image
            image = image.copy()

        try:
            check_aborted(aborted)
            
            # Call remote API for OCR
            response = self._api_client.recognize_image(
                image=image,
                max_tokens=max_output_tokens or 4096,
                enhanced_table_mode=True
            )
            
            # Get usage info
            usage = self._api_client.get_usage_info(response)
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            
            # Extract text content
            text_content = self._api_client.extract_text_content(response)
            
            check_aborted(aborted)
            
            if text_content and text_content.strip():
                # Create a simple layout from the OCR result
                # This is a simplified approach - we treat the entire result as text
                normalized_text = self._normalize_text(text_content)
                
                if normalized_text:
                    # Determine if this looks like a table
                    if self._is_table_content(normalized_text):
                        ref = "table"
                    else:
                        ref = "text"
                    
                    # Create layout covering the entire image
                    width, height = image.size
                    layout = PageLayout(
                        ref=ref,
                        det=(0, 0, width, height),
                        text=normalized_text,
                        hash=None,
                        order=0,
                    )
                    body_layouts.append(layout)
            
            # For footnotes, we would need additional processing
            # For now, we don't extract footnotes from remote API results
            
            return Page(
                index=page_index,
                image=raw_image,
                body_layouts=body_layouts,
                footnotes_layouts=footnotes_layouts,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            
        except Exception as error:
            raise OCRError(
                f"Failed to extract page {page_index} with remote API.",
                page_index=page_index,
                step_index=1,
            ) from error

    def _normalize_text(self, text: str | None) -> str:
        """Normalize text output from remote API"""
        if text is None:
            return ""
        text = remove_surrogates(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _is_table_content(self, text: str) -> bool:
        """Simple heuristic to detect if content looks like a table"""
        # Look for table indicators
        table_indicators = [
            "|",  # Markdown table pipes
            "表1", "表2", "表3", "表4",  # Chinese table labels
            "Table 1", "Table 2",  # English table labels
        ]
        
        for indicator in table_indicators:
            if indicator in text:
                return True
        
        # Look for structured data patterns
        lines = text.split('\n')
        if len(lines) > 3:
            # Check if multiple lines have similar structure (might be table rows)
            structured_lines = 0
            for line in lines:
                if ':' in line or '：' in line or '|' in line:
                    structured_lines += 1
            
            if structured_lines > 2:
                return True
        
        return False