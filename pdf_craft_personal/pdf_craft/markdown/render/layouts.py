import re
from pathlib import Path
from shutil import copy2
from typing import Iterable, Generator, Callable, Optional, Union

from ...pdf import TITLE_TAGS
from ..paragraph import render_markdown_paragraph
from ...expression import to_markdown_string, ExpressionKind
from ...sequence import (
    Reference,
    AssetLayout,
    ParagraphLayout,
    InlineExpression,
    BlockMember,
    RefIdMap,
)
from ...ai_api.config import APIConfig

_MAX_TOC_LEVELS = 3
_MAX_TITLE_LEVELS = 6




def render_layouts(
        layouts: Iterable[Union[ParagraphLayout, AssetLayout]],
        assets_path: Path,
        output_assets_path: Path,
        asset_ref_path: Path,
        toc_level: int,
        ref_id_to_number: Optional[RefIdMap] = None,
        config: Optional[APIConfig] = None,
    ) -> Generator[str, None, None]:

    is_first_layout = True
    toc_level = min(toc_level, _MAX_TOC_LEVELS - 1)

    for layout in layouts:
        if is_first_layout:
            is_first_layout = False
        else:
            yield "\n\n"
        if isinstance(layout, AssetLayout):
            yield from _render_asset(
                asset=layout,
                assets_path=assets_path,
                output_assets_path=output_assets_path,
                asset_ref_path=asset_ref_path,
                ref_id_to_number=ref_id_to_number,
                config=config,
            )
        elif isinstance(layout, ParagraphLayout):
            yield from render_paragraph(
                paragraph=layout,
                toc_level=toc_level,
                ref_id_to_number=ref_id_to_number,
            )

def render_paragraph(paragraph: ParagraphLayout, toc_level: int, ref_id_to_number: Optional[RefIdMap] = None) -> Generator[str, None, None]:
    is_title = paragraph.level >= 0 and paragraph.ref in TITLE_TAGS
    
    if is_title:
        level = min(toc_level + paragraph.level, _MAX_TITLE_LEVELS)
        for _ in range(level + 1): # level 0 对应 1 个 #
            yield "#"
        yield " "

    def render_member(part: Union[BlockMember, str]) -> Generator[str, None, None]:
        if isinstance(part, str):
            yield to_markdown_string(
                kind=ExpressionKind.TEXT,
                content=part,
            )
        elif isinstance(part, InlineExpression):
            latex_content = part.content.strip()
            if latex_content:
                yield to_markdown_string(
                    kind=part.kind,
                    content=latex_content,
                )
        elif ref_id_to_number and isinstance(part, Reference):
            ref_number = ref_id_to_number.get(part.id, 1)
            yield "[^"
            yield str(ref_number)
            yield "]"

    for block in paragraph.blocks:
        yield from render_markdown_paragraph(
            children=block.content,
            render_payload=render_member,
        )
    
    # 如果是标题，在内容后添加换行符
    if is_title:
        yield "\n"

_MemberRender = Callable[[Union[BlockMember, str]], Iterable[str]]

def _render_asset(
    asset: AssetLayout,
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
    ref_id_to_number: Optional[RefIdMap] = None,
    config: Optional[APIConfig] = None,
) -> Generator[str, None, None]:

    def render_member(part: Union[BlockMember, str]) -> Generator[str, None, None]:
        if isinstance(part, str):
            yield to_markdown_string(
                kind=ExpressionKind.TEXT,
                content=part,
            )
        elif isinstance(part, InlineExpression):
            latex_content = part.content.strip()
            if latex_content:
                yield to_markdown_string(
                    kind=part.kind,
                    content=latex_content,
                )
        elif ref_id_to_number and isinstance(part, Reference):
            ref_number = ref_id_to_number.get(part.id, 1)
            yield "[^"
            yield str(ref_number)
            yield "]"

    has_content = False

    if asset.title:
        title_str = "".join(render_markdown_paragraph(
            children=asset.title,
            render_payload=render_member,
        )).strip()
        if title_str:
            yield title_str
            has_content = True

    yield from _render_asset_content(
        asset=asset,
        assets_path=assets_path,
        output_assets_path=output_assets_path,
        asset_ref_path=asset_ref_path,
        render_member=render_member,
        has_content_before=has_content,
        config=config,
    )
    if asset.ref in ("equation", "table"):
        if asset.content:
            has_content = True
    elif asset.ref == "image":
        if asset.hash:
            has_content = True

    if asset.caption:
        caption_str = "".join(render_markdown_paragraph(
            children=asset.caption,
            render_payload=render_member,
        )).strip()
        if caption_str:
            if has_content:
                yield "\n\n"
            yield caption_str

def _render_asset_content(
    asset: AssetLayout,
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
    render_member: _MemberRender,
    has_content_before: bool,
    config: Optional[APIConfig] = None,
) -> Generator[str, None, None]:

    if asset.ref == "equation":
        content_str = "".join(render_markdown_paragraph(
            children=asset.content,
            render_payload=render_member,
        ))
        latex_content = content_str.strip()
        if latex_content:
            if has_content_before:
                yield "\n\n"
            yield to_markdown_string(
                kind=ExpressionKind.DISPLAY_BRACKET,
                content=latex_content,
            )

    elif asset.ref == "table":
        if asset.content:
            if has_content_before:
                yield "\n\n"
            
            # 根据配置决定表格渲染模式
            table_render_mode = "html"  # 默认值
            if config and hasattr(config, 'table_render_mode'):
                table_render_mode = config.table_render_mode
            
            if table_render_mode == "markdown":
                # 尝试将HTML表格转换为Markdown表格
                try:
                    markdown_table = _convert_html_table_to_markdown(asset.content, render_member)
                    if markdown_table:
                        yield markdown_table
                    else:
                        # 如果转换失败，回退到原来的HTML渲染
                        yield from render_markdown_paragraph(
                            children=asset.content,
                            render_payload=render_member,
                        )
                except Exception:
                    # 转换出错时，回退到原来的HTML渲染
                    yield from render_markdown_paragraph(
                        children=asset.content,
                        render_payload=render_member,
                    )
            else:
                # HTML模式，直接渲染HTML
                yield from render_markdown_paragraph(
                    children=asset.content,
                    render_payload=render_member,
                )

    elif asset.ref == "image":
        yield from _render_image(
            asset=asset,
            assets_path=assets_path,
            output_assets_path=output_assets_path,
            asset_ref_path=asset_ref_path,
            has_content_before=has_content_before,
        )

def _render_image(
    asset: AssetLayout,
    assets_path: Path,
    output_assets_path: Path,
    asset_ref_path: Path,
    has_content_before: bool,
) -> Generator[str, None, None]:
    # 渲染图片
    if asset.hash is None:
        return

    source_file = assets_path / f"{asset.hash}.png"
    if not source_file.exists():
        return

    target_file = output_assets_path / f"{asset.hash}.png"
    if not target_file.exists():
        copy2(source_file, target_file)

    if asset_ref_path.is_absolute():
        image_path = target_file
    else:
        image_path = asset_ref_path / f"{asset.hash}.png"

    # 使用 POSIX 风格路径(markdown 标准)
    image_path_str = str(image_path).replace("\\", "/")

    # 图片的 alt 保持空
    if has_content_before:
        yield "\n\n"
    yield f"![]({image_path_str})"


def _convert_html_table_to_markdown(content, render_member) -> str:
    """将HTML表格转换为Markdown表格格式
    
    Args:
        content: 表格的HTML内容，可能是字符串或者BlockMember列表
        render_member: 内容渲染函数
    
    Returns:
        转换后的Markdown表格字符串，失败时返回None
    """
    import re
    try:
        from xml.etree.ElementTree import fromstring, ParseError as XMLSyntaxError
    except ImportError:
        from xml.etree.ElementTree import fromstring
        XMLSyntaxError = Exception
    
    try:
        # 渲染表格内容为字符串
        if hasattr(content, '__iter__') and not isinstance(content, str):
            # 如果content是BlockMember列表，渲染为字符串
            from ..paragraph import render_markdown_paragraph
            html_content = "".join(render_markdown_paragraph(
                children=content,
                render_payload=render_member,
            ))
        else:
            html_content = str(content)
        
        # 提取HTML表格
        table_match = re.search(r'<table[^>]*>(.*?)</table>', html_content, re.Union[DOTALL, re].IGNORECASE)
        if not table_match:
            return None
            
        table_html = "<table>" + table_match.group(1) + "</table>"
        
        # 解析HTML表格
        try:
            # 包装在一个根元素中以确保有效的XML
            wrapped_html = f"<root>{table_html}</root>"
            root = fromstring(wrapped_html)
            table_elem = root.find('.//table')
            if table_elem is None:
                return None
                
        except XMLSyntaxError:
            # 如果XML解析失败，尝试简单的正则表达式解析
            return _parse_table_with_regex(table_html)
        
        # 提取表格数据
        rows = []
        for tr in table_elem.findall('.//tr'):
            row = []
            for cell in tr.findall('.//td') + tr.findall('.//th'):
                cell_text = _extract_text_from_element(cell).strip()
                row.append(cell_text)
            if row:  # 只添加非空行
                rows.append(row)
        
        if not rows:
            return None
            
        # 转换为Markdown表格
        return _format_markdown_table(rows)
        
    except Exception:
        # 任何解析错误都返回None，回退到HTML渲染
        return None


def _parse_table_with_regex(table_html: str) -> str:
    """使用正则表达式解析HTML表格（备用方案）"""
    import re
    
    try:
        # 提取所有行
        tr_pattern = r'<tr[^>]*>(.*?)</tr>'
        rows = []
        
        for tr_match in re.finditer(tr_pattern, table_html, re.Union[DOTALL, re].IGNORECASE):
            row_html = tr_match.group(1)
            
            # 提取单元格
            cell_pattern = r'<t[hd][^>]*>(.*?)</t[hd]>'
            cells = []
            for cell_match in re.finditer(cell_pattern, row_html, re.Union[DOTALL, re].IGNORECASE):
                cell_content = cell_match.group(1)
                # 移除HTML标签
                cell_text = re.sub(r'<[^>]+>', '', cell_content).strip()
                cells.append(cell_text)
            
            if cells:
                rows.append(cells)
        
        if rows:
            return _format_markdown_table(rows)
        return None
        
    except Exception:
        return None


def _extract_text_from_element(element) -> str:
    """从XML元素中提取纯文本"""
    text = element.text or ""
    for child in element:
        text += _extract_text_from_element(child)
        text += child.tail or ""
    return text


def _format_markdown_table(rows) -> str:
    """将表格数据格式化为Markdown表格"""
    if not rows:
        return ""
    
    # 确定列数
    max_cols = max(len(row) for row in rows)
    
    # 填充空缺的单元格
    for row in rows:
        while len(row) < max_cols:
            row.append("")
    
    # 计算每列的最大宽度
    col_widths = []
    for col_idx in range(max_cols):
        max_width = max(len(str(row[col_idx])) for row in rows)
        col_widths.append(max(max_width, 3))  # 最小宽度为3
    
    # 生成Markdown表格
    markdown_lines = []
    
    # 表格数据行
    for row_idx, row in enumerate(rows):
        # 格式化行
        formatted_cells = []
        for col_idx, cell in enumerate(row):
            cell_str = str(cell)
            # 转义Markdown特殊字符
            cell_str = cell_str.replace('|', '\\|').replace('\n', ' ')
            formatted_cells.append(f" {cell_str:<{col_widths[col_idx]}} ")
        
        markdown_lines.append("|" + "|".join(formatted_cells) + "|")
        
        # 在第一行后添加分隔行
        if row_idx == 0:
            separator_cells = []
            for col_idx in range(max_cols):
                separator_cells.append("-" * (col_widths[col_idx] + 2))
            markdown_lines.append("|" + "|".join(separator_cells) + "|")
    
    return "\n".join(markdown_lines)

