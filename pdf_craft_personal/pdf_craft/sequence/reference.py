import re

from typing import Iterable, Optional, Union

from .chapter import Reference, BlockLayout, AssetLayout, ParagraphLayout
from .content import Content
from .mark import transform2mark, Mark


_START_PREFIX_PATTERN = re.compile(r"^\*{1,6}\s+")

class References:
    def __init__(self, page_index: int, layouts: Iterable[Union[AssetLayout, ParagraphLayout]]) -> None:
        self._page_index: int = page_index
        self._references: list[Reference] = list(self._extract_references(page_index, layouts))
        self._mark2reference: dict[Union[str, Mark], Reference] = {}
        for reference in self._references:
            mark = reference.mark
            if mark not in self._mark2reference:
                self._mark2reference[mark] = reference

    @property
    def page_index(self) -> int:
        return self._page_index

    def get(self, mark: Union[str, Mark]) -> Optional[Reference]:
        return self._mark2reference.get(mark, None)

    def _extract_references(self, page_index: int, layouts: Iterable[Union[AssetLayout, ParagraphLayout]]):
        order: int = 1
        reference: Optional[Reference] = None
        for item in self._iter_and_inject_marks(layouts):
            if isinstance(item, Union[Mark, str]):
                if reference:
                    yield reference
                reference = Reference(
                    page_index=page_index,
                    order=order,
                    mark=item,
                    layouts=[],
                )
                order += 1
            elif reference:
                reference.layouts.append(item)
            else:
                # TODO: 多余的内容可能是上一页的跨页页脚注释 / 引用，也可能是必须忽略的多余内容。
                #       此处没有能力进行判断，以后看看有什么好办法。
                pass
        if reference:
            yield reference

    def _iter_and_inject_marks(self, layouts: Iterable[Union[AssetLayout, ParagraphLayout]]):
        for layout in layouts:
            if isinstance(layout, AssetLayout):
                yield layout
            elif isinstance(layout, ParagraphLayout):
                for mark, sub_layout in self._split_paragraph_by_marks(layout):
                    if mark is not None:
                        yield mark
                    yield sub_layout

    def _split_paragraph_by_marks(self, to_split_layout: ParagraphLayout):
        mark_layout: tuple[Union[Mark, Optional[str]], ParagraphLayout] = (
            None,
            ParagraphLayout(
                ref=to_split_layout.ref,
                level=-1,
                blocks=[],
            ),
        )
        for block in to_split_layout.blocks:
            mark, content = self._extract_head_mark(block.content)
            if mark is None:
                mark_layout[1].blocks.append(block)
            else:
                if mark_layout[1].blocks:
                    yield mark_layout
                mark_layout = (mark, ParagraphLayout(
                    ref=to_split_layout.ref,
                    level=-1,
                    blocks=[BlockLayout(
                        page_index=block.page_index,
                        order=block.order,
                        det=block.det,
                        content=content,
                    )],
                ))
        if mark_layout[1].blocks:
            yield mark_layout

    def _extract_head_mark(self, content: Content) -> tuple[Union[Mark, Optional[str]], Content]:
        if not content or not isinstance(content[0], str):
            return None, content
        head_text = content[0].lstrip()
        if not head_text:
            return None, content

        mark: Union[Mark, Optional[str]] = None
        rest: str = ""
        matched = _START_PREFIX_PATTERN.match(head_text)
        new_content: Content = content[1:]

        if matched:
            prefix = matched.group(0)
            mark = prefix.strip()
            rest = head_text[matched.end():].lstrip()
        else:
            mark = transform2mark(head_text[0])
            if mark is not None:
                rest = head_text[1:].lstrip()

        rest = rest.lstrip()
        if rest:
            new_content = [rest] + content[1:]

        return mark, new_content
