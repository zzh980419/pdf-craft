"""
按页渲染PDF为Markdown的功能模块
每页作为独立单元处理，不进行跨页拼接
"""

from pathlib import Path
from typing import List, Generator, Callable, Optional
from shutil import copy2

from ..pdf import Page, PageLayout, TITLE_TAGS, decode as decode_page
from ..common import read_xml
from ..ai_api.config import APIConfig
from .paragraph import render_markdown_paragraph
from ..expression import to_markdown_string, ExpressionKind, parse_latex_expressions


def render_page_to_markdown(
    page: Page,
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
    config: Optional[APIConfig] = None,
) -> str:
    """将单个页面渲染为Markdown字符串
    
    Args:
        page: 页面对象
        assets_path: 资源源路径
        output_assets_path: 资源输出路径  
        asset_ref_path: 资源引用路径
        config: API配置
        
    Returns:
        该页的Markdown字符串
    """
    parts = list(_render_page_layouts(
        layouts=page.body_layouts,
        assets_path=assets_path,
        output_assets_path=output_assets_path,
        asset_ref_path=asset_ref_path,
        config=config,
    ))
    
    # 添加脚注处理
    if page.footnotes_layouts:
        parts.append("\n\n---\n\n## 脚注")
        footnote_parts = list(_render_page_layouts(
            layouts=page.footnotes_layouts,
            assets_path=assets_path,
            output_assets_path=output_assets_path,
            asset_ref_path=asset_ref_path,
            config=config,
        ))
        parts.extend(footnote_parts)
    
    return "".join(parts)


def _render_page_layouts(
    layouts: List[PageLayout],
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
    config: Optional[APIConfig] = None,
) -> Generator[str, None, None]:
    """渲染页面布局为Markdown
    
    Args:
        layouts: 页面布局列表
        assets_path: 资源源路径
        output_assets_path: 资源输出路径
        asset_ref_path: 资源引用路径
        config: API配置
    """
    is_first_layout = True
    
    for layout in layouts:
        if is_first_layout:
            is_first_layout = False
        else:
            yield "\n\n"
            
        if layout.ref in ("table", "image"):
            # 处理资源布局
            yield from _render_page_asset(
                layout=layout,
                assets_path=assets_path,
                output_assets_path=output_assets_path,
                asset_ref_path=asset_ref_path,
                config=config,
            )
        else:
            # 处理段落布局
            yield from _render_page_paragraph(layout)


def _render_page_paragraph(layout: PageLayout) -> Generator[str, None, None]:
    """渲染页面段落
    
    Args:
        layout: 页面布局对象
    """
    is_title = layout.ref in TITLE_TAGS
    
    if is_title:
        # 根据ref类型确定标题级别
        if layout.ref == "title":
            level = 1
        elif layout.ref == "sub_title":  
            level = 2
        else:
            level = 1
            
        for _ in range(level):
            yield "#"
        yield " "
    
    # 处理文本内容
    text = layout.text.strip()
    if text:
        # 解析LaTeX表达式
        parsed_items = parse_latex_expressions(text)
        for item in parsed_items:
            if isinstance(item, str):
                yield to_markdown_string(
                    kind=ExpressionKind.TEXT,
                    content=item,
                )
            else:
                # 处理数学公式等表达式
                latex_content = item.content.strip()
                if latex_content:
                    yield to_markdown_string(
                        kind=item.kind,
                        content=latex_content,
                    )
    
    # 如果是标题，在内容后添加换行符
    if is_title:
        yield "\n"


def _render_page_asset(
    layout: PageLayout,
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
    config: Optional[APIConfig] = None,
) -> Generator[str, None, None]:
    """渲染页面资源（表格、图片等）
    
    Args:
        layout: 页面布局对象
        assets_path: 资源源路径
        output_assets_path: 资源输出路径
        asset_ref_path: 资源引用路径
        config: API配置
    """
    if layout.ref == "table":
        yield from _render_page_table(layout, config)
    elif layout.ref == "image":
        yield from _render_page_image(
            layout=layout,
            assets_path=assets_path,
            output_assets_path=output_assets_path,
            asset_ref_path=asset_ref_path,
        )


def _render_page_table(layout: PageLayout, config: Optional[APIConfig] = None) -> Generator[str, None, None]:
    """渲染页面表格
    
    Args:
        layout: 页面布局对象
        config: API配置
    """
    table_render_mode = "html"  # 默认值
    if config and hasattr(config, 'table_render_mode'):
        table_render_mode = config.table_render_mode
    
    if table_render_mode == "markdown":
        # 尝试将HTML表格转换为Markdown表格
        try:
            from .layouts import _convert_html_table_to_markdown
            
            def dummy_render_member(part):
                if isinstance(part, str):
                    yield part
                else:
                    yield str(part)
            
            markdown_table = _convert_html_table_to_markdown(layout.text, dummy_render_member)
            if markdown_table:
                yield markdown_table
                return
        except Exception:
            pass
    
    # 默认或转换失败时，直接输出HTML表格内容
    yield layout.text


def _render_page_image(
    layout: PageLayout,
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
) -> Generator[str, None, None]:
    """渲染页面图片
    
    Args:
        layout: 页面布局对象
        assets_path: 资源源路径
        output_assets_path: 资源输出路径
        asset_ref_path: 资源引用路径
    """
    if layout.hash is None:
        return
    
    source_file = assets_path / f"{layout.hash}.png"
    if not source_file.exists():
        return
    
    # 确保输出目录存在
    output_assets_path.mkdir(parents=True, exist_ok=True)
    
    target_file = output_assets_path / f"{layout.hash}.png"
    if not target_file.exists():
        copy2(source_file, target_file)
    
    if asset_ref_path.is_absolute():
        image_path = target_file
    else:
        image_path = asset_ref_path / f"{layout.hash}.png"
    
    # 使用POSIX风格路径(markdown标准)
    image_path_str = str(image_path).replace("\\", "/")
    
    # 图片的alt保持空
    yield f"![]({image_path_str})"


def load_page_from_xml(page_xml_path: Path) -> Page:
    """从XML文件加载页面对象
    
    Args:
        page_xml_path: 页面XML文件路径
        
    Returns:
        页面对象
    """
    return decode_page(read_xml(page_xml_path))