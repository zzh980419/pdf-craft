"""
Remote API client for PDF-Craft
"""

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
    """AI API error base class"""
    pass


class RateLimitError(APIError):
    """API rate limit error"""
    pass


class QuotaExceededError(APIError):
    """API quota exceeded error"""
    pass


class AIAPIClient:
    """AI API client
    
    Used for calling DeepSeek OCR API for document recognition
    """
    
    def __init__(self, config: Optional[APIConfig] = None):
        """Initialize AI API client
        
        Args:
            config: API configuration, if not provided, will load automatically
        """
        self.config = config or load_config()
        self.session = requests.Session()
        
        # Set request headers based on provider
        headers = {"Content-Type": "application/json"}
        if self.config.provider == "DEEPSEEK_OCR" and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        self.session.headers.update(headers)
    
    def recognize_image(
        self,
        image: Image.Image,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        enhanced_table_mode: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Recognize document content in image
        
        Args:
            image: PIL image object
            model: Model name to use, defaults to default_model in config
            max_tokens: Maximum number of tokens
            enhanced_table_mode: Whether to use enhanced table recognition prompts
            **kwargs: Other API parameters
            
        Returns:
            Dict: API response result
            
        Raises:
            APIError: Raised when API call fails
        """
        if model is None:
            model = self.config.default_model
        
        # Convert image to base64
        image_b64 = self._image_to_base64(image, enhanced_table_mode)
        
        # Choose prompt based on table mode - simplified for DeepSeek-OCR
        if enhanced_table_mode:
            prompt_text = "请提取图片中的所有文字。如果有表格请用markdown格式输出。"
        else:
            prompt_text = "请提取图片中的所有文字。"
        
        # Build request data for DeepSeek OCR
        request_data = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_text
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
            "temperature": 0.1,  # Very low temperature to reduce hallucination
            "top_p": 0.1,       # Low top_p for more focused output
            "max_tokens": max_tokens if max_tokens else 2048,  # Reasonable token limit
            "frequency_penalty": 0.5,  # Penalize repetition
            "presence_penalty": 0.3    # Encourage diverse content
        }
        
        # Add optional parameters
        if max_tokens:
            request_data["max_tokens"] = max_tokens
        
        # Merge other parameters
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
        """Recognize text content
        
        Args:
            images: Image list or text list
            prompt: Prompt text
            model: Model name to use
            max_tokens: Maximum number of tokens
            **kwargs: Other API parameters
            
        Returns:
            str: Recognition result text
        """
        if model is None:
            model = self.config.default_model
        
        # Build request data for DeepSeek API
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
        
        # Add optional parameters
        if max_tokens:
            request_data["max_tokens"] = max_tokens
        
        # Merge other parameters
        request_data.update(kwargs)
        
        # Execute request and extract text content
        response = self._make_request(request_data)
        return self.extract_text_content(response)
    
    def _image_to_base64(self, image: Image.Image, enhanced_table_mode: bool = False) -> str:
        """Convert PIL image to base64 string"""
        if self.config.debug:
            print(f"Converting image to base64: {image.size}, mode: {image.mode}")
            
        # Ensure image is in RGB format
        if image.mode != "RGB":
            image = image.convert("RGB")
            if self.config.debug:
                print(f"Converted image mode to RGB")
        
        # Save image to memory
        buffer = BytesIO()
        
        # Optimize image for better OCR accuracy
        width, height = image.size
        
        # For table recognition, use higher resolution and quality
        if enhanced_table_mode:
            max_size = 2048  # Higher resolution for tables
            quality = 90     # Higher quality for better table recognition
        else:
            max_size = 1536  # Increased standard resolution
            quality = 75     # Increased standard quality
        
        # Resize if needed
        if max(width, height) > max_size:
            ratio = max_size / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            if self.config.debug:
                print(f"Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Save with appropriate quality
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        
        # Convert to base64
        image_bytes = buffer.getvalue()
        base64_str = base64.b64encode(image_bytes).decode('utf-8')
        
        if self.config.debug:
            print(f"Base64 encoded image size: {len(base64_str)} chars")
        
        return base64_str
    
    def _make_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute API request with retry mechanism"""
        # Build URL for DeepSeek OCR
        url = f"{self.config.base_url.rstrip('/')}/v1/chat/completions"
        
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                if self.config.debug:
                    print(f"AI API request (attempt {attempt + 1}/{self.config.max_retries + 1}): {url}")
                
                response = self.session.post(
                    url,
                    json=data,
                    timeout=self.config.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if self.config.debug:
                        print(f"AI API response success: {result.get('usage', {})}")
                    return result
                
                elif response.status_code == 429:
                    # Rate limit error, need to wait and retry
                    if attempt < self.config.max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        if self.config.debug:
                            print(f"API rate limited, waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RateLimitError("API request rate limit exceeded")
                
                elif response.status_code == 402:
                    raise QuotaExceededError("API quota exhausted")
                
                elif response.status_code >= 500:
                    # Server error, can retry
                    if attempt < self.config.max_retries:
                        wait_time = 2 ** attempt
                        if self.config.debug:
                            print(f"Server error {response.status_code}, waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise APIError(f"Server error: {response.status_code}")
                
                else:
                    # Client error, generally no retry
                    error_msg = f"API request failed: {response.status_code}"
                    try:
                        error_detail = response.json()
                        error_msg += f" - {error_detail}"
                    except:
                        error_msg += f" - {response.text}"
                    raise APIError(error_msg)
            
            except requests.exceptions.Timeout as e:
                last_error = APIError(f"API request timeout: {e}")
                if attempt < self.config.max_retries:
                    if self.config.debug:
                        print(f"Request timeout, waiting before retry...")
                    time.sleep(2 ** attempt)
                    continue
            
            except requests.exceptions.RequestException as e:
                last_error = APIError(f"Network request failed: {e}")
                if attempt < self.config.max_retries:
                    if self.config.debug:
                        print(f"Network error, waiting before retry...")
                    time.sleep(2 ** attempt)
                    continue
        
        # All retries failed
        if last_error:
            raise last_error
        else:
            raise APIError("API request failed, reached maximum retry attempts")
    
    def extract_text_content(self, api_response: Dict[str, Any]) -> str:
        """Extract text content from API response
        
        Args:
            api_response: API response data
            
        Returns:
            str: Extracted text content
        """
        try:
            if self.config.debug:
                print(f"API Response structure: {list(api_response.keys())}")
            
            choices = api_response.get("choices", [])
            if not choices:
                if self.config.debug:
                    print("Warning: No choices in API response")
                    print(f"Full response: {api_response}")
                return ""
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            if self.config.debug:
                print(f"Extracted content length: {len(content)}")
                if len(content) < 50:
                    print(f"Content preview: '{content}'")
            
            # Check if content is empty or just whitespace
            stripped_content = content.strip()
            if not stripped_content:
                if self.config.debug:
                    print("Warning: API returned empty content")
                    print(f"Original response: {api_response}")
                return ""
            
            return stripped_content
        
        except Exception as e:
            raise APIError(f"Failed to parse API response: {e}")
    
    def get_usage_info(self, api_response: Dict[str, Any]) -> Dict[str, int]:
        """Get API call usage information
        
        Args:
            api_response: API response data
            
        Returns:
            Dict: Dictionary containing input_tokens and output_tokens
        """
        usage = api_response.get("usage", {})
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }