"""
并发PDF处理器

实现页面级别的并发处理，大幅提升转换速度
"""

import concurrent.futures
import time
import threading
from typing import List, Dict, Any, Callable, Container, Optional
from pathlib import Path
import sys
from queue import Queue

from .pdf.ocr import OCR, OCREvent, OCREventKind
from .pdf.page_ref import PageRefContext
from .common import AssetHub, save_xml
from .pdf.types import encode, DeepSeekOCRSize
from .metering import check_aborted, AbortedCheck, OCRTokensMetering
from .error import PDFError, OCRError, IgnorePDFErrorsChecker, IgnoreOCRErrorsChecker


class ConcurrentPDFProcessor:
    """并发PDF处理器"""
    
    def __init__(
        self,
        ocr: OCR,
        max_workers: int = 3,
        batch_size: int = 3,
    ):
        self.ocr = ocr
        self.max_workers = max_workers
        self.batch_size = batch_size
        self._results_lock = threading.Lock()
        
    def process_pdf_concurrent(
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
        on_ocr_event: Callable[[OCREvent], None] = lambda _: None,
    ):
        """并发处理PDF页面"""
        
        ocr_path.mkdir(parents=True, exist_ok=True)
        if plot_path is not None:
            plot_path.mkdir(parents=True, exist_ok=True)

        done_path = ocr_path / "done"
        if done_path.exists():
            return OCRTokensMetering(0, 0)

        # 收集需要处理的页面
        pages_to_process = []
        
        with PageRefContext(
            pdf_path=pdf_path,
            pdf_handler=self.ocr._get_pdf_handler(),
        ) as refs:
            pages_count = refs.pages_count
            asset_hub = AssetHub(asset_path)
            
            for ref in refs:
                if ref.page_index not in page_indexes:
                    continue
                    
                filename = f"page_{ref.page_index}.xml"
                file_path = ocr_path / filename
                
                if not file_path.exists():
                    pages_to_process.append({
                        'ref': ref,
                        'file_path': file_path,
                        'page_index': ref.page_index
                    })

        if not pages_to_process:
            done_path.touch()
            return OCRTokensMetering(0, 0)

        # 并发处理页面
        total_metering = OCRTokensMetering(0, 0)
        processed_pages = {}
        
        print(f"开始并发处理 {len(pages_to_process)} 页 (并发数: {self.max_workers})")
        
        # 分批并发处理
        for i in range(0, len(pages_to_process), self.batch_size):
            check_aborted(aborted)
            batch = pages_to_process[i:i + self.batch_size]
            
            print(f"处理批次 {i//self.batch_size + 1}/{(len(pages_to_process) + self.batch_size - 1)//self.batch_size}: "
                  f"页面 {batch[0]['page_index']}-{batch[-1]['page_index']}")
            
            batch_results = self._process_batch_concurrent(
                batch=batch,
                asset_hub=asset_hub,
                ocr_size=ocr_size,
                dpi=dpi,
                max_page_image_file_size=max_page_image_file_size,
                includes_footnotes=includes_footnotes,
                plot_path=plot_path,
                cover_path=cover_path,
                max_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                ignore_pdf_errors=ignore_pdf_errors,
                ignore_ocr_errors=ignore_ocr_errors,
                pages_count=pages_count,
                aborted=aborted,
            )
            
            # 处理批次结果
            for i, page_info in enumerate(batch):
                page_index = page_info['page_index']
                file_path = page_info['file_path']
                result = batch_results.get(i, {'error': Exception(f"页面{page_index}处理失败"), 'elapsed_ms': 0})
                
                if 'error' in result:
                    # 发送错误事件
                    on_ocr_event(OCREvent(
                        kind=OCREventKind.FAILED,
                        page_index=page_index,
                        total_pages=pages_count,
                        cost_time_ms=result.get('elapsed_ms', 0),
                        error=result['error']
                    ))
                else:
                    # 保存页面数据
                    page = result['page']
                    save_xml(encode(page), file_path)
                    
                    # 处理封面
                    if (cover_path and page.image and page_index == 1 and 
                        not cover_path.exists()):
                        cover_path.parent.mkdir(parents=True, exist_ok=True)
                        page.image.save(cover_path, format="PNG")
                    
                    # 累计token使用
                    total_metering.input_tokens += page.input_tokens
                    total_metering.output_tokens += page.output_tokens
                    
                    # 发送完成事件
                    on_ocr_event(OCREvent(
                        kind=OCREventKind.COMPLETE,
                        page_index=page_index,
                        total_pages=pages_count,
                        cost_time_ms=result.get('elapsed_ms', 0),
                        input_tokens=page.input_tokens,
                        output_tokens=page.output_tokens
                    ))

        # 标记完成
        done_path.touch()
        return total_metering

    def _process_batch_concurrent(
        self,
        batch: List[Dict],
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_footnotes: bool,
        plot_path: Optional[Path],
        cover_path: Optional[Path],
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        pages_count: int,
        aborted: AbortedCheck,
    ) -> Dict:
        """并发处理一批页面"""
        
        # 尝试使用批量API处理
        if hasattr(self.ocr, '_batch_service') and self.ocr._batch_service and len(batch) > 1:
            try:
                return self._process_batch_api(
                    batch=batch,
                    asset_hub=asset_hub,
                    ocr_size=ocr_size,
                    dpi=dpi,
                    max_page_image_file_size=max_page_image_file_size,
                    includes_footnotes=includes_footnotes,
                    max_tokens=max_tokens,
                    max_output_tokens=max_output_tokens,
                    ignore_pdf_errors=ignore_pdf_errors,
                    ignore_ocr_errors=ignore_ocr_errors,
                    aborted=aborted,
                )
            except Exception as e:
                print(f"批量API处理失败，回退到并发处理: {e}")
        
        # 回退到原有的并发处理
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_index = {}
            for i, page_info in enumerate(batch):
                future = executor.submit(
                    self._process_single_page,
                    page_info=page_info,
                    asset_hub=asset_hub,
                    ocr_size=ocr_size,
                    dpi=dpi,
                    max_page_image_file_size=max_page_image_file_size,
                    includes_footnotes=includes_footnotes,
                    plot_path=plot_path,
                    max_tokens=max_tokens,
                    max_output_tokens=max_output_tokens,
                    ignore_pdf_errors=ignore_pdf_errors,
                    ignore_ocr_errors=ignore_ocr_errors,
                    aborted=aborted,
                )
                future_to_index[future] = i
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    results[index] = result
                except Exception as e:
                    results[index] = {'error': e, 'elapsed_ms': 0}
        
        return results

    def _process_batch_api(
        self,
        batch: List[Dict],
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_footnotes: bool,
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        aborted: AbortedCheck,
    ) -> Dict:
        """使用批量API处理一批页面"""
        
        start_time = time.perf_counter()
        
        try:
            check_aborted(aborted)
            
            # 准备批量数据
            pages_data = []
            for page_info in batch:
                page_ref = page_info['ref']
                
                # 渲染页面图像
                image = page_ref.render(
                    dpi=dpi if dpi is not None else 300,
                    max_image_file_size=max_page_image_file_size,
                )
                
                pages_data.append({
                    'image': image,
                    'page_index': page_info['page_index'],
                    'asset_hub': asset_hub,
                    'includes_raw_image': (page_info['page_index'] == 1),
                    'plot_path': None,  # 批量模式暂不支持plot_path
                })
            
            # 使用批量OCR服务
            pages = self.ocr._batch_service.process_pages_batch(
                pages_data=pages_data,
                ocr_size=ocr_size,
                includes_footnotes=includes_footnotes,
                max_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                aborted=aborted,
            )
            
            # 构建结果字典
            results = {}
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            for i, page_info in enumerate(batch):
                if i < len(pages):
                    results[i] = {
                        'page': pages[i],
                        'elapsed_ms': elapsed_ms // len(batch)  # 平均分配时间
                    }
                else:
                    results[i] = {
                        'error': Exception(f"批量处理页面 {page_info['page_index']} 失败"),
                        'elapsed_ms': elapsed_ms // len(batch)
                    }
            
            return results
            
        except Exception as e:
            # 批量处理失败，返回错误结果
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            results = {}
            for i, page_info in enumerate(batch):
                results[i] = {
                    'error': e,
                    'elapsed_ms': elapsed_ms // len(batch)
                }
            return results

    def _process_single_page(
        self,
        page_info: Dict,
        asset_hub: AssetHub,
        ocr_size: DeepSeekOCRSize,
        dpi: Optional[int],
        max_page_image_file_size: Optional[int],
        includes_footnotes: bool,
        plot_path: Optional[Path],
        max_tokens: Optional[int],
        max_output_tokens: Optional[int],
        ignore_pdf_errors: IgnorePDFErrorsChecker,
        ignore_ocr_errors: IgnoreOCRErrorsChecker,
        aborted: AbortedCheck,
    ) -> Dict:
        """处理单个页面"""
        
        start_time = time.perf_counter()
        page_ref = page_info['ref']
        page_index = page_info['page_index']
        
        try:
            check_aborted(aborted)
            
            # 渲染页面图像
            image = page_ref.render(
                dpi=dpi if dpi is not None else 300,
                max_image_file_size=max_page_image_file_size,
            )
            
            # 检查token限制
            if max_tokens is not None and max_tokens <= 0:
                from doc_page_extractor import TokenLimitError
                raise TokenLimitError()
            if max_output_tokens is not None and max_output_tokens <= 0:
                from doc_page_extractor import TokenLimitError
                raise TokenLimitError()

            # OCR处理
            page = self.ocr._ocr_service.image2page(
                image=image,
                page_index=page_index,
                asset_hub=asset_hub,
                ocr_size=ocr_size,
                includes_footnotes=includes_footnotes,
                includes_raw_image=(page_index == 1),
                plot_path=plot_path,
                max_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                device_number=None,
                aborted=aborted,
            )
            
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                'page': page,
                'elapsed_ms': elapsed_ms
            }
            
        except (PDFError, OCRError) as error:
            # 检查是否应该忽略错误
            should_ignore = False
            if isinstance(error, PDFError):
                should_ignore = self._check_ignore_error(ignore_pdf_errors, error)
            else:  # OCRError
                should_ignore = self._check_ignore_error(ignore_ocr_errors, error)
            
            if not should_ignore:
                raise
                
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                'error': error,
                'elapsed_ms': elapsed_ms
            }

    def _check_ignore_error(self, ignore_checker, error):
        """检查是否应该忽略错误"""
        if callable(ignore_checker):
            return ignore_checker(error)
        return bool(ignore_checker)