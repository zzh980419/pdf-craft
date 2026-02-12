from dataclasses import dataclass
import re

from typing import cast, Generator, Iterable, Optional, Union

from ..expression import parse_latex_expressions, ExpressionKind, ParsedItem

from ..pdf import TITLE_TAGS, PageLayout
from ..common import ASSET_TAGS, AssetRef
from ..language import is_latin_letter
from ..markdown.paragraph import parse_raw_markdown

from .chapter import ParagraphLayout, AssetLayout, BlockLayout, InlineExpression
from .content import first, last, expand_text_in_content, Content
from .reading_serials import split_reading_serials


_ASSET_CAPTION_TAGS = tuple(f"{t}_caption" for t in ASSET_TAGS)

# to see https://github.com/opendatalab/MinerU/blob/fa1149cd4abf9db5e0f13e4e074cdb568be189f4/mineru/utils/span_pre_proc.py#L247
_LINE_STOP_FLAGS = (
    ".", "!", "?", "。", "！", "？", ")", "）", """, """, ";", "；",
    "]", "】", "}", ">", "》",
)

_LINE_CONTINUE_FLAGS = (
    "[", "【", "{", "<", "《", "、", ",", "，",
)

_LINK_FLAGS = (
    "‐", "‑", "‒", "–", "—", "―",
)

_MARKDOWN_HEAD_PATTERN = re.compile(r"^#+\s+")
_TABLE_PATTERN = re.compile(r"<table[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)


@dataclass
class _LastTail:
    page_para: ParagraphLayout
    override: list[AssetLayout]

@dataclass
class _AssetHolder:
    page_index: int
    ref: AssetRef
    det: tuple[int, int, int, int]
    title: Optional[str]
    content: str
    caption: Optional[str]
    hash: Optional[str]


class Jointer:
    def __init__(self, layouts: Iterable[tuple[int, list[PageLayout]]]) -> None:
        self._layouts = layouts

    def execute(self) -> Generator[Union[ParagraphLayout, AssetLayout], None, None]:
        last_tail: Optional[_LastTail] = None

        for page_index, raw_layouts in self._iter_layout_serials():
            # 此处为完成如下业务要求：
            # 1. 当阅读序列跨越 group（跨页、跨分栏、跨因图片而挤变形拆分的段落）时，必须对连接处验证。若它们是被拆分的自然段，则拼起来。
            # 2. 因为插图、表格而拆分的自然段，需将插图存起来接到完整的自然段最后，而不是任其分割自然段。
            layouts = list(self._join_and_handle_asset_layouts(page_index, raw_layouts))
            head, body, tail = self._split_layouts(layouts)

            if not body:
                if last_tail:
                    last_tail.override.extend(head)
                    last_tail.override.extend(tail)
                else:
                    yield from head
                    yield from tail
                continue

            first_layout = cast(ParagraphLayout, body[0])
            if last_tail and self._can_merge_paragraphs(last_tail.page_para, first_layout):
                last_tail.page_para.blocks.extend(first_layout.blocks)
                del body[0]

            if not body:
                if last_tail:
                    last_tail.override.extend(head)
                    last_tail.override.extend(tail)
                else:
                    yield from head
                    yield from tail
                continue

            # 至此，连续吞并段落的流程遇阻而结束
            if last_tail:
                _normalize_paragraph_content(last_tail.page_para)
                yield last_tail.page_para
                yield from last_tail.override
                last_tail = None

            yield from head
            for i in range(len(body) - 1):
                yield body[i]

            last_tail = _LastTail(
                page_para=cast(ParagraphLayout, body[-1]),
                override=list(tail),
            )

        if last_tail:
            _normalize_paragraph_content(last_tail.page_para)
            yield last_tail.page_para
            yield from last_tail.override

    def _iter_layout_serials(self) -> Generator[tuple[int, list[PageLayout]], None, None]:
        for page_index, raw_layouts in self._layouts:
            for layouts in split_reading_serials(raw_layouts):
                yield page_index, layouts

    def _split_layouts(self, layouts: list[Union[ParagraphLayout, AssetLayout]]):
        head: list[AssetLayout] = []
        tail: list[AssetLayout] = []

        for layout in layouts:
            if isinstance(layout, ParagraphLayout):
                break
            head.append(layout)

        for i in range(len(layouts) - 1, -1, -1):
            if i < len(head):
                break
            layout = layouts[i]
            if isinstance(layout, ParagraphLayout):
                break
            tail.append(layout)

        tail.reverse()
        body = layouts[len(head):len(layouts) - len(tail)]

        return head, body, tail

    def _join_and_handle_asset_layouts(self, page_index, layouts: list[PageLayout]) -> Generator[Union[ParagraphLayout, AssetLayout], None, None]:
        # layout 可能被后续处理，必须等待所有 layout 处理完毕
        for layout in list(self._join_asset_layouts(
            page_index=page_index,
            layouts=layouts,
        )):
            if not isinstance(layout, _AssetHolder):
                yield layout
                continue

            if layout.ref == "equation":
                _normalize_equation(layout)
            if layout.ref == "table":
                _normalize_table(layout)

            yield AssetLayout(
                page_index=page_index,
                ref=layout.ref,
                det=layout.det,
                title=_parse_block_content(layout.title),
                content=_parse_block_content(layout.content),
                caption=_parse_block_content(layout.caption),
                hash=layout.hash,
            )

    def _join_asset_layouts(self, page_index, layouts: list[PageLayout]):
        last_asset: Optional[_AssetHolder] = None
        i = 0
        while i < len(layouts):
            layout = layouts[i]
            
            if layout.ref in ASSET_TAGS:
                if last_asset:
                    yield last_asset
                last_asset = _AssetHolder(
                    page_index=page_index,
                    ref=layout.ref,
                    det=layout.det,
                    title=None,
                    content=layout.text,
                    caption=None,
                    hash=layout.hash,
                )
                i += 1
            elif layout.ref in _ASSET_CAPTION_TAGS:
                if last_asset:
                    if last_asset.caption:
                        last_asset.caption += "\n" + layout.text
                    else:
                        last_asset.caption = layout.text
                i += 1
            else:
                if last_asset:
                    yield last_asset
                    last_asset = None
                
                # Check if this is a title layout that contains table headers
                # and the next layout is a text layout that contains table data
                if (layout.ref == "title" and _is_text_table(layout.text) and 
                    i + 1 < len(layouts) and 
                    layouts[i + 1].ref == "text" and 
                    _is_text_table(layouts[i + 1].text)):
                    
                    next_layout = layouts[i + 1]
                    # Combine the title (headers) and text (data) into a single table
                    # Remove any newlines from the title to avoid empty cells
                    title_text = layout.text.strip().replace('\n', '')
                    text_content = next_layout.text.strip()
                    combined_table_content = title_text + "\n" + text_content
                    
                    # Calculate combined detection area
                    x1 = min(layout.det[0], next_layout.det[0])
                    y1 = min(layout.det[1], next_layout.det[1])
                    x2 = max(layout.det[2], next_layout.det[2])
                    y2 = max(layout.det[3], next_layout.det[3])
                    combined_det = (x1, y1, x2, y2)
                    
                    table_asset = _AssetHolder(
                        page_index=page_index,
                        ref="table",
                        det=combined_det,
                        title=None,
                        content=combined_table_content,
                        caption=None,
                        hash=layout.hash,
                    )
                    # Process the table
                    _normalize_table(table_asset)
                    
                    yield AssetLayout(
                        page_index=page_index,
                        ref="table",
                        det=table_asset.det,
                        title=_parse_block_content(table_asset.title),
                        content=_parse_block_content(table_asset.content),
                        caption=_parse_block_content(table_asset.caption),
                        hash=table_asset.hash,
                    )
                    # Skip the next layout since we've already processed it
                    i += 2
                
                # Check if this text content might actually be a table that was misclassified
                elif layout.ref == "text" and _is_text_table(layout.text):
                    # Convert misclassified table to proper table asset
                    table_asset = _AssetHolder(
                        page_index=page_index,
                        ref="table",
                        det=layout.det,
                        title=None,
                        content=layout.text,
                        caption=None,
                        hash=layout.hash,
                    )
                    # Process the table
                    _normalize_table(table_asset)
                    
                    yield AssetLayout(
                        page_index=page_index,
                        ref="table",
                        det=table_asset.det,
                        title=_parse_block_content(table_asset.title),
                        content=_parse_block_content(table_asset.content),
                        caption=_parse_block_content(table_asset.caption),
                        hash=table_asset.hash,
                    )
                    i += 1
                else:
                    # Normal text processing
                    if layout.ref in TITLE_TAGS:
                        # 将 Markdown 标题前的 `##` 之类的符号删除，DeepSeek OCR 总会生成这种符号
                        layout.text = _MARKDOWN_HEAD_PATTERN.sub("", layout.text)

                    yield ParagraphLayout(
                        ref=layout.ref,
                        level=-1,
                        blocks=[BlockLayout(
                            page_index=page_index,
                            order=layout.order,
                            det=layout.det,
                            content=_parse_block_content(layout.text),
                        )],
                    )
                    i += 1
        if last_asset:
            yield last_asset

    # too see https://github.com/opendatalab/MinerU/blob/fa1149cd4abf9db5e0f13e4e074cdb568be189f4/mineru/backend/pipeline/para_split.py#L253
    def _can_merge_paragraphs(self, para1: ParagraphLayout, para2: ParagraphLayout) -> bool:
        if para1.ref != "text":
            return False
        if para1.ref != para2.ref:
            return False

        block1 = para1.blocks[-1]
        block2 = para2.blocks[0]

        text1 = last(block1.content)
        text2 = first(block2.content)
        if not isinstance(text1, str) or not isinstance(text2, str):
            return False

        text1_stripped = text1.rstrip()
        text2_stripped = text2.lstrip()
        if not text1_stripped or not text2_stripped:
            return False

        # 条件1：前一个段落如果以句尾符号结尾，说明是完整段落，不应合并
        if text1_stripped.endswith(_LINE_STOP_FLAGS):
            return False

        # 条件2：前一个段落结束的符号明显表明句子未结束，则必须合并
        if text1_stripped.endswith(_LINE_CONTINUE_FLAGS):
            return True

        first_char = text2_stripped[0]

        # 条件3：下一个段落的第一个字符不是数字
        # 如果以数字开头，可能是编号列表的新段落（如"1. xxx"）
        if first_char.isdigit():
            return False

        # 条件4：下一个段落的第一个字符不是大写字母
        # 如果以大写字母开头，可能是新段落的开始（特别是英文）
        if first_char.isupper():
            return False

        # 条件5：如果 para1 结尾是拉丁字母 + `-`，para2 开头是拉丁字母，则允许合并（跨段单词拼接）
        if is_latin_letter(text2[0]):
            if len(text1) >= 2 and text1[-1] in _LINK_FLAGS and \
               is_latin_letter(text1[-2]):
                return True
            if is_latin_letter(text1[-1]):
                return False

        return True

def _normalize_equation(layout: _AssetHolder):
    if layout.ref != "equation" or not layout.content:
        return

    found_first_expression: bool = False
    expression_content: str = ""
    prefix_texts: list[str] = []
    tail_items: list[ParsedItem] = []

    for item in parse_latex_expressions(layout.content):
        if not found_first_expression and item.kind != ExpressionKind.TEXT:
            expression_content = item.content
            found_first_expression = True
        elif found_first_expression:
            tail_items.append(item)
        else:
            prefix_texts.append(item.content)

    if not found_first_expression:
        return

    if layout.title is not None:
        prefix_texts.insert(0, layout.title)

    if layout.caption is not None:
        tail_items.append(ParsedItem(kind=ExpressionKind.TEXT, content=layout.caption))

    if prefix_texts:
        layout.title = "".join(prefix_texts)

    layout.content = expression_content

    if tail_items:
        layout.caption = "".join(item.reverse() for item in tail_items)


def _normalize_table(layout: _AssetHolder):
    found_table_content: Optional[str] = None
    head_buffer: list[str] = []
    tail_buffer: list[str] = []

    for part in (layout.title, "\n", layout.content, "\n", layout.caption):
        if not part:
            continue

        table_match = _TABLE_PATTERN.search(part)
        if not table_match:
            if found_table_content is None:
                head_buffer.append(part)
            else:
                tail_buffer.append(part)
            continue

        table_start = table_match.start()
        table_end = table_match.end()

        table_content = part[table_start:table_end]
        before = part[:table_start].rstrip()
        after = part[table_end:].lstrip()

        if before.strip():
            head_buffer.append(before)
        if after.strip():
            tail_buffer.append(after)

        found_table_content = table_content

    if not found_table_content:
        # No HTML table found, check if content looks like a text-based table
        content_text = layout.content or ""
        if _is_text_table(content_text):
            # Convert text table to HTML
            html_table = _convert_text_table_to_html(content_text)
            if html_table:
                layout.content = html_table
        return

    head = "".join(head_buffer).strip()
    tail = "".join(tail_buffer).strip()

    layout.title = head if head else None
    layout.caption = tail if tail else None
    layout.content = found_table_content

# 将单词的连接符 `-` 删去，并将后半节单词移到前面一段拼接
def _normalize_paragraph_content(paragraph: ParagraphLayout):
    if len(paragraph.blocks) < 2:
        return

    for i in range(1, len(paragraph.blocks)):
        block1 = paragraph.blocks[i - 1]
        block2 = paragraph.blocks[i]

        text1 = last(block1.content)
        text2 = first(block2.content)
        if not isinstance(text1, str) or not isinstance(text2, str):
            continue

        text1 = text1.rstrip()
        text2 = text2.lstrip()
        if not _is_splitted_word(text1, text2):
            continue

        tail_end = 0
        for j in range(len(text2)):
            if is_latin_letter(text2[j]):
                tail_end = j + 1
            else:
                break

        block1.content[-1] = text1[:-1] + text2[:tail_end]
        block2.content[0] = text2[tail_end:].lstrip()
        if not block2.content[0]:
            del block2.content[0]

    # 极端情况下 block2 会因为单词被移走而被清空。此时要将其整个删去。
    paragraph.blocks = [block for block in paragraph.blocks if block.content]

def _parse_block_content(text: Optional[str]) -> Content:
    if not text:
        return []

    root_content: Content = parse_raw_markdown(text)

    def expand_text(text: str):
        for item in parse_latex_expressions(text):
            if item.kind != ExpressionKind.TEXT:
                yield InlineExpression(
                    kind=item.kind,
                    content=item.content,
                )
            elif item.content: # Only add non-empty strings
                yield item.content

    expand_text_in_content(
        content=root_content,
        expand=expand_text,
    )
    return root_content

def _is_text_table(text: str) -> bool:
    """Check if the text looks like a pipe-delimited table."""
    if not text or '|' not in text:
        return False
    
    # Check if text has table-like structure with pipes
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    table_lines = 0
    
    for line in lines:
        # Count pipes in the line
        pipe_count = line.count('|')
        
        # A table row should have at least 2 pipes (for at least 1 cell)
        # and should start/end with pipes or have content between pipes
        if pipe_count >= 2:
            # Check if it looks Union[like, content]|Union[content, or] has separators like |---|---|
            if (line.startswith('|') and line.endswith('|')) or '---' in line or '--' in line:
                table_lines += 1
    
    # Consider it a table if at least one line looks like a table row
    return table_lines > 0


def _convert_text_table_to_html(text: str) -> str:
    """Convert text-based table to HTML format."""
    if not text.strip():
        return ""
    
    # Split text into lines first to handle multi-line table structures
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not lines:
        return ""
    
    all_rows = []
    
    for line in lines:
        # Split by pipe characters and clean up
        parts = [part.strip() for part in line.split('|')]
        
        # Remove empty parts from start/end that come from leading/trailing pipes
        while parts and not parts[0]:
            parts.pop(0)
        while parts and not parts[-1]:
            parts.pop()
        
        # Skip lines that are just separators (like |---|---|---|)
        if all(part in ['', '----', '---', '--', '-', '－', '——'] for part in parts):
            continue
            
        # Only add non-empty rows
        if parts:
            # Convert empty strings to empty cells
            row_cells = [part if part else "" for part in parts]
            all_rows.append(row_cells)
    
    if not all_rows:
        return ""
    
    # Find the maximum number of columns across all rows
    max_cols = max(len(row) for row in all_rows)
    
    if max_cols == 0:
        return ""
    
    # Normalize all rows to have the same number of columns
    for row in all_rows:
        while len(row) < max_cols:
            row.append("")
    
    # Build HTML table
    html_parts = ["<table>"]
    
    for i, row in enumerate(all_rows):
        html_parts.append("<tr>")
        
        # Use <th> for the first row (header) and <td> for data rows
        cell_tag = "th" if i == 0 else "td"
        
        for cell in row:
            # Escape HTML entities in cell content
            if cell:
                escaped_cell = cell.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(f"<{cell_tag}>{escaped_cell}</{cell_tag}>")
            else:
                html_parts.append(f"<{cell_tag} />")  # Self-closing tag for empty cells
                
        html_parts.append("</tr>")
    
    html_parts.append("</table>")
    return "".join(html_parts)


def _is_splitted_word(text1: str, text2: str) -> bool:
    return (
        len(text1) >= 2 and text1[-1] in _LINK_FLAGS and \
        is_latin_letter(text1[-2]) and \
        is_latin_letter(text2[0])
    )
