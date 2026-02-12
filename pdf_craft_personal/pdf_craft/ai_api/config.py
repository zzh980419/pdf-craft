import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class APIConfig:
    provider: str  # AI提供商: "volc" 或 "deepseek"
    base_url: str
    api_key: str
    default_model: str
    timeout: int = 30
    max_retries: int = 3
    debug: bool = False
    # 表格渲染配置
    table_render_mode: str = "html"  # "html" 或 "markdown"


def get_env_bool(key: str, default: bool = False) -> bool:
    """从环境变量获取布尔值"""
    load_env_config()  # 确保环境变量已加载
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def load_env_config(env_path: Optional[Path] = None) -> None:
    """加载环境变量配置（供其他模块使用）"""
    if env_path is None:
        # 查找项目根目录的.env文件
        current_dir = Path(__file__).parent
        while current_dir != current_dir.parent:
            env_file = current_dir / ".env"
            if env_file.exists():
                env_path = env_file
                break
            current_dir = current_dir.parent

    # 加载.env文件
    if env_path and env_path.exists():
        _load_env_file(env_path)


def load_config(env_path: Optional[Path] = None) -> APIConfig:
    """加载AI API配置

    Args:
        env_path: .env文件路径，默认为项目根目录的.env文件

    Returns:
        APIConfig: 配置对象

    Raises:
        ValueError: 必需的配置项缺失时抛出
    """
    # 首先加载环境变量
    load_env_config(env_path)

    # 获取AI提供商配置
    provider = os.getenv("OCR_PROVIDER", "DEEPSEEK_OCR")
    if provider not in ("VOLC", "DEEPSEEK_OCR"):
        raise ValueError(f"不支持的AI提供商: {provider}，请选择 'VOLC' 或 'DEEPSEEK_OCR'")

    # 根据提供商获取相应的配置
    if provider == "VOLC":
        base_url = os.getenv("VOLC_BASE_URL")
        api_key = os.getenv("VOLC_API_KEY")
        default_model = os.getenv("VOLC_OCR_MODEL")

        if not base_url:
            raise ValueError("VOLC_BASE_URL环境变量未设置")
        if not api_key:
            raise ValueError("VOLC_API_KEY环境变量未设置")
        if not default_model:
            raise ValueError("VOLC_OCR_MODEL环境变量未设置")

    elif provider == "DEEPSEEK_OCR":
        base_url = os.getenv("DEEPSEEK_OCR_BASE_URL")
        api_key = os.getenv("DEEPSEEK_OCR_API_KEY", "")  # DeepSeek本地部署不需要key
        default_model = os.getenv("DEEPSEEK_OCR_MODEL")

        if not base_url:
            raise ValueError("DEEPSEEK_OCR_BASE_URL环境变量未设置")
        if not default_model:
            raise ValueError("DEEPSEEK_OCR_MODEL环境变量未设置")

    # 获取可选配置
    timeout = int(os.getenv("OCR_API_TIMEOUT", "120"))
    max_retries = 1  # 默认重试1次
    debug = False    # 默认关闭调试模式

    # 获取表格渲染配置
    table_render_mode = os.getenv("TABLE_RENDER_MODE", "html").lower()
    # 验证表格渲染模式
    if table_render_mode not in ("html", "markdown"):
        table_render_mode = "html"  # 默认回退到html

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
    """加载.env文件中的环境变量"""
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # 处理行内注释
                if "#" in value:
                    value = value.split("#")[0].strip()

                # 只有在环境变量不存在时才设置
                if key not in os.environ:
                    os.environ[key] = value
