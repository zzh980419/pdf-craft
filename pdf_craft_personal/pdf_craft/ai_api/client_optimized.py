"""
优化版AI API客户端

主要优化：
1. HTTP连接池复用
2. 图像处理优化
3. 请求批量化
4. 智能重试
"""

import json
import time
import base64
from io import BytesIO
from typing import Optional, Dict, Any, List
import concurrent.futures
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image

from .config import APIConfig, load_config
from .client import APIError, RateLimitError, QuotaExceededError, AIAPIClient


class OptimizedAIAPIClient(AIAPIClient):
    """优化版AI API客户端"""

    def __init__(self, config: Optional[APIConfig] = None):
        """初始化优化版API客户端"""
        # 调用父类构造函数
        super().__init__(config)
        
        # 替换为优化的session
        self.session.close()  # 关闭原session
        self.session = self._create_optimized_session()
        
        # 图像处理优化
        self._image_cache = {}
        self._cache_lock = threading.Lock()
        
    def _create_optimized_session(self) -> requests.Session:
        """创建优化的HTTP session"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        
        # 配置连接池
        adapter = HTTPAdapter(
            pool_connections=10,  # 连接池数量
            pool_maxsize=20,      # 每个连接池的最大连接数
            max_retries=retry_strategy,
            pool_block=True
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 设置请求头
        session.headers.update({
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "User-Agent": "PDF-Craft-Optimized/1.0"
        })
        
        return session
    
    def recognize_image(
        self,
        image: Image.Image,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """重写父类方法使用优化版本"""
        return self.recognize_image_optimized(image, model, max_tokens, **kwargs)
    
    def recognize_image_optimized(
        self,
        image: Image.Image,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """优化版图像识别"""
        if model is None:
            model = self.config.default_model

        # 优化的图像编码
        image_b64 = self._image_to_base64_optimized(image)

        # 构建请求数据
        request_data = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._get_optimized_prompt()
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "thinking": {
                "type": "disabled"
            },
            "reasoning": {
                "effort": "minimal"
            }
        }

        # 添加可选参数
        if max_tokens:
            request_data["max_tokens"] = max_tokens

        # 合并其他参数
        request_data.update(kwargs)

        return self._make_optimized_request(request_data)
    
    def _image_to_base64(self, image: Image.Image) -> str:
        """重写父类方法使用优化版本"""
        return self._image_to_base64_optimized(image)
    
    def _make_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """重写父类方法使用优化版本"""
        return self._make_optimized_request(data)
    
    def recognize_images_batch_api(
        self,
        images: List[Image.Image],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """真正的批量API调用 - 单个请求处理多张图片"""
        if model is None:
            model = self.config.default_model

        # 将所有图像转换为base64
        image_urls = []
        for image in images:
            image_b64 = self._image_to_base64_optimized(image)
            image_urls.append(f"data:image/jpeg;base64,{image_b64}")

        # 构建批量请求 - 所有图像在一个content数组中
        content_items = [
            {
                "type": "text",
                "text": f"请分别识别以下{len(images)}张图片中的文档内容。每张图片的结果请用 '=== PAGE N ===' 的格式分隔（N为页码，从1开始）。要求：\n1. 输出HTML格式的表格（使用<table><tr><td>标签）\n2. 保持原有文档结构和层次\n3. 公式用LaTeX语法包裹在$$中\n4. 标题用#标记层级"
            }
        ]
        
        # 添加所有图像
        for i, image_url in enumerate(image_urls):
            content_items.append({
                "type": "image_url", 
                "image_url": {"url": image_url}
            })

        request_data = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content_items
                }
            ],
            "thinking": {"type": "disabled"},
            "reasoning": {"effort": "minimal"}
        }

        if max_tokens:
            request_data["max_tokens"] = max_tokens * len(images)  # 为多图预留更多token

        request_data.update(kwargs)
        return self._make_optimized_request(request_data)

    def recognize_images_batch(
        self,
        images_data: List[tuple],  # [(image, page_index, options), ...]
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """批量图像识别（并发处理）"""
        if model is None:
            model = self.config.default_model
            
        results = []
        
        # 限制并发数避免API限流
        max_workers = min(3, len(images_data))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_data = {}
            for image_data in images_data:
                image, page_index, options = image_data
                future = executor.submit(
                    self.recognize_image_optimized,
                    image=image,
                    model=model,
                    **options
                )
                future_to_data[future] = (page_index, image_data)
            
            # 收集结果
            page_results = {}
            for future in concurrent.futures.as_completed(future_to_data):
                page_index, image_data = future_to_data[future]
                try:
                    result = future.result()
                    page_results[page_index] = result
                except Exception as e:
                    page_results[page_index] = {"error": str(e)}
            
            # 按页面顺序返回结果
            for image_data in images_data:
                page_index = image_data[1]
                results.append(page_results.get(page_index, {"error": "未知错误"}))
        
        return results

    def _image_to_base64_optimized(self, image: Image.Image) -> str:
        """优化版图像转base64"""
        # 创建缓存键
        image_hash = hash((image.tobytes(), image.size, image.mode))
        
        with self._cache_lock:
            if image_hash in self._image_cache:
                return self._image_cache[image_hash]
        
        # 确保图像为RGB格式
        if image.mode != "RGB":
            image = image.convert("RGB")

        # 智能压缩策略
        width, height = image.size
        max_size = 1536
        quality = 80  # 提高质量，减少重复压缩

        # 更智能的尺寸调整
        if max(width, height) > max_size:
            ratio = max_size / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            # 使用更高质量的重采样算法
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 优化的压缩设置
        buffer = BytesIO()
        
        # 根据图像内容调整压缩参数
        if width * height > 1000000:  # 大图像使用更高压缩
            quality = 70
        
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        image_bytes = buffer.getvalue()
        
        # 转换为base64
        b64_string = base64.b64encode(image_bytes).decode('utf-8')
        
        # 缓存结果（限制缓存大小）
        with self._cache_lock:
            if len(self._image_cache) > 50:
                # 移除最旧的缓存
                self._image_cache.pop(next(iter(self._image_cache)))
            self._image_cache[image_hash] = b64_string
        
        return b64_string

    def _get_optimized_prompt(self) -> str:
        """获取优化的提示词"""
        return """请识别这张图片中的文档内容，要求：
1. 输出HTML格式的表格（使用<table><tr><td>标签）
2. 保持原有文档结构和层次  
3. 公式用LaTeX语法包裹在$$中
4. 标题用#标记层级
5. 保持原文语言和格式
6. 识别准确，格式清晰"""

    def _make_optimized_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """优化版API请求"""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        
        # 优化的超时设置
        timeout = (10, self.config.timeout)  # (连接超时, 读取超时)
        
        try:
            if self.config.debug:
                print(f"发送优化API请求: {url}")

            response = self.session.post(
                url,
                json=data,
                timeout=timeout
            )

            if response.status_code == 200:
                result = response.json()
                if self.config.debug:
                    usage = result.get('usage', {})
                    print(f"API响应成功: 输入{usage.get('prompt_tokens', 0)}, "
                          f"输出{usage.get('completion_tokens', 0)} tokens")
                return result

            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', '2'))
                time.sleep(min(retry_after, 10))  # 最多等待10秒
                raise RateLimitError("API请求频率超限，请稍后重试")

            elif response.status_code == 402:
                raise QuotaExceededError("API配额已用完")

            else:
                error_msg = f"API请求失败: {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text}"
                raise APIError(error_msg)

        except requests.exceptions.Timeout:
            raise APIError("API请求超时")
        except requests.exceptions.RequestException as e:
            raise APIError(f"网络请求失败: {e}")

    def extract_text_content(self, api_response: Dict[str, Any]) -> str:
        """从API响应中提取文本内容"""
        try:
            choices = api_response.get("choices", [])
            if not choices:
                return ""

            message = choices[0].get("message", {})
            content = message.get("content", "")

            return content.strip()

        except Exception as e:
            raise APIError(f"解析API响应失败: {e}")

    def get_usage_info(self, api_response: Dict[str, Any]) -> Dict[str, int]:
        """获取API调用的使用情况信息"""
        usage = api_response.get("usage", {})
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'session'):
            self.session.close()