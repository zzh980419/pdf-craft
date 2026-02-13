"""
Remote API module for PDF-Craft

This module provides remote API functionality that replaces local model calls with remote API calls.
It maintains the same interface as the original project.
"""

from .config import APIConfig, load_config
from .client import AIAPIClient, APIError, RateLimitError, QuotaExceededError
from .remote_ocr import RemoteOCR
from .remote_extractor import RemotePageExtractorNode
from .simple_transform import transform_pdf_to_markdown_remote
from .table_aware_parser import TableAwarePageParser

__all__ = [
    # Configuration
    'APIConfig',
    'load_config', 
    
    # Client
    'AIAPIClient',
    'APIError',
    'RateLimitError', 
    'QuotaExceededError',
    
    # Direct replacements for original classes
    'RemoteOCR',
    'RemotePageExtractorNode',
    'transform_pdf_to_markdown_remote',
    'TableAwarePageParser',
]