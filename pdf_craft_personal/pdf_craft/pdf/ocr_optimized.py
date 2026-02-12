"""
优化版OCR处理器

主要优化：
1. 并发处理多页
2. 图像预处理优化
3. 连接复用
4. 智能缓存
"""

import asyncio
import concurrent.futures
import time
from typing import Container, Generator, List, Dict, Any, Optional
from pathlib import Path
import sys
from threading import Lock
import hashlib

from .ocr import OCR, OCREvent, OCREventKind
from .page_ref import PageRefContext
from ..common import AssetHub, save_xml
from ..metering import check_aborted, AbortedCheck
from .types import encode, DeepSeekOCRSize, Page
from ..error import PDFError, OCRError, IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker



class OptimizedOCR(OCR):
    """优化版OCR处理器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._processed_cache: Dict[str, Page] = {}
        self._cache_lock = Lock()
        self._max_workers = 3  # 并发数量，避免API限流
        
    def recognize_batch(
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
        batch_size: int = 3,  # 批量大小
    ) -> Generator[OCREvent, None, None]:
        """批量并发处理OCR"""
        
        ocr_path.mkdir(parents=True, exist_ok=True)
        if plot_path is not None:
            plot_path.mkdir(parents=True, exist_ok=True)

        done_path = ocr_path / "done"
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
            
            # 收集需要处理的页面
            pages_to_process = []
            for ref in refs:
                if ref.page_index not in page_indexes:
                    continue
                    
                filename = f"page_{ref.page_index}.xml"
                file_path = ocr_path / filename
                
                if not file_path.exists():
                    pages_to_process.append((ref, file_path))

            # 批量并发处理
            total_pages = len(pages_to_process)
            processed_count = 0
            
            for i in range(0, len(pages_to_process), batch_size):
                check_aborted(aborted)
                batch = pages_to_process[i:i + batch_size]
                
                # 并发处理当前批次
                batch_results = self._process_batch(
                    batch=batch,
                    asset_hub=asset_hub,
                    ocr_size=ocr_size,
                    dpi=dpi,
                    max_page_image_file_size=max_page_image_file_size,
                    includes_footnotes=includes_footnotes,
                    plot_path=plot_path,
                    cover_path=cover_path,
                    remain_tokens=remain_tokens,
                    remain_output_tokens=remain_output_tokens,
                    ignore_pdf_errors=ignore_pdf_errors,
                    ignore_ocr_errors=ignore_ocr_errors,
                    pages_count=pages_count,
                    aborted=aborted,
                )
                
                # 处理批次结果
                for page_ref, file_path, result, elapsed_time in batch_results:
                    processed_count += 1
                    
                    if isinstance(result, Exception):
                        yield OCREvent(
                            kind=OCREventKind.FAILED,
                            page_index=page_ref.page_index,
                            total_pages=pages_count,
                            cost_time_ms=elapsed_time,
                            error=result,
                        )
                    else:
                        page, input_tokens, output_tokens = result
                        
                        # 保存页面数据
                        save_xml(encode(page), file_path)
                        
                        # 处理封面
                        if cover_path and page.image and page_ref.page_index == 1:
                            cover_path.parent.mkdir(parents=True, exist_ok=True)
                            page.image.save(cover_path, format="PNG")
                        
                        # 更新token计数
                        if remain_tokens is not None:
                            remain_tokens = max(0, remain_tokens - input_tokens)
                        if remain_output_tokens is not None:
                            remain_output_tokens = max(0, remain_output_tokens - output_tokens)
                        
                        yield OCREvent(
                            kind=OCREventKind.COMPLETE,
                            page_index=page_ref.page_index,
                            total_pages=pages_count,
                            cost_time_ms=elapsed_time,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        )

        # 标记完成
        done_path.touch()

    def _process_batch(
        self,
        batch: List,
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_footnotes: bool,
        plot_path: Optional[Path],
        cover_path: Optional[Path],
        remain_tokens: Optional[int],
        remain_output_tokens: Optional[int],
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        pages_count: int,
        aborted: AbortedCheck,
    ):
        """并发处理一个批次的页面"""
        
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # 提交所有任务
            future_to_page = {}
            for page_ref, file_path in batch:
                future = executor.submit(
                    self._process_single_page_optimized,
                    page_ref=page_ref,
                    asset_hub=asset_hub,
                    ocr_size=ocr_size,
                    dpi=dpi,
                    max_page_image_file_size=max_page_image_file_size,
                    includes_footnotes=includes_footnotes,
                    plot_path=plot_path,
                    remain_tokens=remain_tokens,
                    remain_output_tokens=remain_output_tokens,
                    ignore_pdf_errors=ignore_pdf_errors,
                    ignore_ocr_errors=ignore_ocr_errors,
                    aborted=aborted,
                )
                future_to_page[future] = (page_ref, file_path)
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_page):
                page_ref, file_path = future_to_page[future]
                try:
                    result, elapsed_time = future.result()
                    results.append((page_ref, file_path, result, elapsed_time))
                except Exception as e:
                    results.append((page_ref, file_path, e, 0))
        
        return results

    def _process_single_page_optimized(
        self,
        page_ref,
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_footnotes: bool,
        plot_path: Optional[Path],
        remain_tokens: Optional[int],
        remain_output_tokens: Optional[int],
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        aborted: AbortedCheck,
    ):
        """优化的单页处理"""
        start_time = time.perf_counter()
        
        try:
            # 检查中止状态
            check_aborted(aborted)
            
            # 渲染图像（缓存优化）
            image = self._render_page_with_cache(
                page_ref,
                dpi=dpi if dpi is not None else 300,
                max_image_file_size=max_page_image_file_size,
            )
            
            # 检查token限制
            if remain_tokens is not None and remain_tokens <= 0:
                from doc_page_extractor import TokenLimitError
                raise TokenLimitError()
            if remain_output_tokens is not None and remain_output_tokens <= 0:
                from doc_page_extractor import TokenLimitError
                raise TokenLimitError()

            # OCR处理
            page = self._ocr_service.image2page(
                image=image,
                page_index=page_ref.page_index,
                asset_hub=asset_hub,
                ocr_size=ocr_size,
                includes_footnotes=includes_footnotes,
                includes_raw_image=(page_ref.page_index == 1),
                plot_path=plot_path,
                max_tokens=remain_tokens,
                max_output_tokens=remain_output_tokens,
                device_number=None,
                aborted=aborted,
            )
            
            elapsed_time = int((time.perf_counter() - start_time) * 1000)
            return (page, page.input_tokens, page.output_tokens), elapsed_time
            
        except PDFError as error:
            if not self._check_ignore_error(ignore_pdf_errors, error):
                raise
            elapsed_time = int((time.perf_counter() - start_time) * 1000)
            return error, elapsed_time

        except OCRError as error:
            if not self._check_ignore_error(ignore_ocr_errors, error):
                raise
            elapsed_time = int((time.perf_counter() - start_time) * 1000)
            return error, elapsed_time

    def _render_page_with_cache(self, page_ref, dpi: int, max_image_file_size: Optional[int]):
        """带缓存的页面渲染"""
        # 创建缓存键
        cache_key = hashlib.md5(
            f"{page_ref.page_index}_{dpi}_{max_image_file_size}_{page_ref}".encode()
        ).hexdigest()
        
        with self._cache_lock:
            if cache_key in self._processed_cache:
                return self._processed_cache[cache_key]
        
        # 渲染图像
        image = page_ref.render(
            dpi=dpi,
            max_image_file_size=max_image_file_size,
        )
        
        # 缓存结果（限制缓存大小）
        with self._cache_lock:
            if len(self._processed_cache) > 10:  # 最多缓存10个图像
                # 移除最旧的缓存
                self._processed_cache.pop(next(iter(self._processed_cache)))
            self._processed_cache[cache_key] = image
        
        return image

    def _check_ignore_error(self, ignore_checker, error):
        """检查是否应该忽略错误"""
        if callable(ignore_checker):
            return ignore_checker(error)
        return bool(ignore_checker)