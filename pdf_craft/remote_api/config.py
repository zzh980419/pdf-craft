"""
Remote API configuration module for PDF-Craft
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class APIConfig:
    """Remote API configuration"""
    provider: str  # AI provider: "DEEPSEEK_OCR"
    base_url: str
    api_key: str
    default_model: str
    timeout: int = 120
    max_retries: int = 1
    debug: bool = False
    table_render_mode: str = "html"  # "html" or "markdown"


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean value from environment variables"""
    load_env_config()  # Ensure environment variables are loaded
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def load_env_config(env_path: Optional[Path] = None) -> None:
    """Load environment variables configuration"""
    if env_path is None:
        # Find .env file in project root directory
        current_dir = Path(__file__).parent
        while current_dir != current_dir.parent:
            env_file = current_dir / ".env"
            if env_file.exists():
                env_path = env_file
                break
            current_dir = current_dir.parent

    # Load .env file
    if env_path and env_path.exists():
        _load_env_file(env_path)


def load_config(env_path: Optional[Path] = None) -> APIConfig:
    """Load remote API configuration
    
    Args:
        env_path: Path to .env file, default is project root .env file
        
    Returns:
        APIConfig: Configuration object
        
    Raises:
        ValueError: When required configuration is missing
    """
    # First load environment variables
    load_env_config(env_path)
    
    # Get AI provider configuration
    provider = os.getenv("OCR_PROVIDER", "DEEPSEEK_OCR")
    if provider != "DEEPSEEK_OCR":
        raise ValueError(f"Unsupported AI provider: {provider}, please choose 'DEEPSEEK_OCR'")
    
    # Get DeepSeek OCR configuration
    base_url = os.getenv("DEEPSEEK_OCR_BASE_URL")
    api_key = os.getenv("DEEPSEEK_OCR_API_KEY", "")  # DeepSeek local deployment doesn't need key
    default_model = os.getenv("DEEPSEEK_OCR_MODEL")
    
    if not base_url:
        raise ValueError("DEEPSEEK_OCR_BASE_URL environment variable not set")
    if not default_model:
        raise ValueError("DEEPSEEK_OCR_MODEL environment variable not set")
    
    # Get optional configuration
    timeout = int(os.getenv("OCR_API_TIMEOUT", "120"))
    max_retries = 1  # Default retry 1 time
    debug = os.getenv("OCR_DEBUG", "false").lower() in ("true", "1", "yes")
    
    # Get table rendering configuration
    table_render_mode = os.getenv("TABLE_RENDER_MODE", "html").lower()
    # Validate table rendering mode
    if table_render_mode not in ("html", "markdown"):
        table_render_mode = "html"  # Default fallback to html
    
    return APIConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        timeout=timeout,
        max_retries=max_retries,
        debug=debug,
        table_render_mode=table_render_mode,
    )


def _load_env_file(env_path: Path) -> None:
    """Load environment variables from .env file"""
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # Handle inline comments
                if "#" in value:
                    value = value.split("#")[0].strip()
                
                # Only set if environment variable doesn't exist
                if key not in os.environ:
                    os.environ[key] = value