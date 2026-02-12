import json
import time
import base64
from io import BytesIO
from typing import Optional, Dict, Any, List
from pathlib import Path

import requests
from PIL import Image

from .config import APIConfig, load_config


class APIError(Exception):
    """AI API错误基类"""
    pass


class RateLimitError(APIError):
    """API限流错误"""
    pass


class QuotaExceededError(APIError):
    """配额超出错误"""
    pass


class AIAPIClient:
    """AI API客户端

    用于调用Volc AI API进行OCR和文档识别
    """

    def __init__(self, config: Optional[APIConfig] = None):
        """初始化AI API客户端

        Args:
            config: API配置，如果不提供则自动加载
        """
        self.config = config or load_config()
        self.session = requests.Session()

        # 根据提供商设置请求头
        headers = {"Content-Type": "application/json"}
        if self.config.provider == "VOLC" and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == "DEEPSEEK_OCR" and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        self.session.headers.update(headers)

    def recognize_image(
        self,
        image: Image.Image,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """识别图像中的文档内容

        Args:
            image: PIL图像对象
            model: 使用的模型名称，默认使用配置中的default_model
            max_tokens: 最大token数量
            **kwargs: 其他API参数

        Returns:
            Dict: API响应结果

        Raises:
            APIError: API调用失败时抛出
        """
        if model is None:
            model = self.config.default_model

        # 将图像转换为base64
        image_b64 = self._image_to_base64(image)

        # 构建请求数据，根据不同提供商调整格式
        if self.config.provider == "DEEPSEEK_OCR":
            # DeepSeek OCR 专用配置
            request_data = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请准确识别图片中的文字内容，按原文逐字输出。"
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
                "stream": False,
                "temperature": 0,
                "top_p": 0.9,
                "max_tokens": max_tokens if max_tokens else 4096
            }
        else:
            # 火山引擎豆包API格式
            request_data = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请准确识别图片中的文字内容，按原文输出，保持文档结构。要求：\n1. 准确识别所有文字\n2. 保持原有排版结构\n3. 表格用Markdown格式输出\n4. 保持原始语言\n5. 不要添加任何说明或解释"
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
                "reasoning": {"effort": "minimal"}
            }

        # 添加可选参数
        if max_tokens:
            request_data["max_tokens"] = max_tokens

        # 合并其他参数
        request_data.update(kwargs)

        return self._make_request(request_data)

    def recognize_text(
        self,
        images: List[str],
        prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """识别文本内容

        Args:
            images: 图像列表或文本列表
            prompt: 提示文本
            model: 使用的模型名称
            max_tokens: 最大token数量
            **kwargs: 其他API参数

        Returns:
            str: 识别结果文本
        """
        if model is None:
            model = self.config.default_model

        # 构建请求数据，根据不同提供商调整格式
        if self.config.provider == "DEEPSEEK_OCR":
            # DeepSeek API格式
            request_data = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "stream": False
            }
        else:
            # 火山引擎豆包API格式
            request_data = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "thinking": {
                    "type": "disabled"
                },
                "reasoning": {"effort": "minimal"}
            }

        # 添加可选参数
        if max_tokens:
            request_data["max_tokens"] = max_tokens

        # 合并其他参数
        request_data.update(kwargs)

        # 执行请求并提取文本内容
        response = self._make_request(request_data)
        return self.extract_text_content(response)

    def _image_to_base64(self, image: Image.Image) -> str:
        """将PIL图像转换为base64字符串"""
        # 确保图像为RGB格式
        if image.mode != "RGB":
            image = image.convert("RGB")

        # 将图像保存到内存中
        buffer = BytesIO()

        # 压缩图像以减少传输大小，针对DeepSeek-OCR优化
        width, height = image.size
        max_size = 1024 if self.config.provider == "DEEPSEEK_OCR" else 1536  # DeepSeek使用更小的尺寸

        if max(width, height) > max_size:
            ratio = max_size / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 保存为JPEG格式，针对不同提供商调整压缩
        quality = 65 if self.config.provider == "DEEPSEEK_OCR" else 75  # DeepSeek使用更高压缩
        image.save(buffer, format="JPEG", quality=quality, optimize=True)

        # 转换为base64
        image_bytes = buffer.getvalue()
        return base64.b64encode(image_bytes).decode('utf-8')

    def _make_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """执行API请求，包含重试机制"""
        # 根据提供商构建不同的URL
        if self.config.provider == "DEEPSEEK_OCR":
            url = f"{self.config.base_url.rstrip('/')}/v1/chat/completions"
        else:
            url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                if self.config.debug:
                    print(f"AI API请求 (尝试 {attempt + 1}/{self.config.max_retries + 1}): {url}")

                response = self.session.post(
                    url,
                    json=data,
                    timeout=self.config.timeout
                )

                if response.status_code == 200:
                    result = response.json()
                    if self.config.debug:
                        print(f"AI API响应成功: {result.get('usage', {})}")
                    return result

                elif response.status_code == 429:
                    # 限流错误，需要等待后重试
                    if attempt < self.config.max_retries:
                        wait_time = 2 ** attempt  # 指数退避
                        if self.config.debug:
                            print(f"API限流，等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RateLimitError("API请求频率超限")

                elif response.status_code == 402:
                    raise QuotaExceededError("API配额已用完")

                elif response.status_code >= 500:
                    # 服务器错误，可以重试
                    if attempt < self.config.max_retries:
                        wait_time = 2 ** attempt
                        if self.config.debug:
                            print(f"服务器错误 {response.status_code}，等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise APIError(f"服务器错误: {response.status_code}")

                else:
                    # 客户端错误，一般不重试
                    error_msg = f"API请求失败: {response.status_code}"
                    try:
                        error_detail = response.json()
                        error_msg += f" - {error_detail}"
                    except:
                        error_msg += f" - {response.text}"
                    raise APIError(error_msg)

            except requests.exceptions.Timeout as e:
                last_error = APIError(f"API请求超时: {e}")
                if attempt < self.config.max_retries:
                    if self.config.debug:
                        print(f"请求超时，等待后重试...")
                    time.sleep(2 ** attempt)
                    continue

            except requests.exceptions.RequestException as e:
                last_error = APIError(f"网络请求失败: {e}")
                if attempt < self.config.max_retries:
                    if self.config.debug:
                        print(f"网络错误，等待后重试...")
                    time.sleep(2 ** attempt)
                    continue

        # 所有重试都失败了
        if last_error:
            raise last_error
        else:
            raise APIError("API请求失败，已达到最大重试次数")

    def extract_text_content(self, api_response: Dict[str, Any]) -> str:
        """从API响应中提取文本内容

        Args:
            api_response: API响应数据

        Returns:
            str: 提取的文本内容
        """
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
        """获取API调用的使用情况信息

        Args:
            api_response: API响应数据

        Returns:
            Dict: 包含input_tokens和output_tokens的字典
        """
        usage = api_response.get("usage", {})
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
