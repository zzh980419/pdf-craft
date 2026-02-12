import re
import io

from dataclasses import dataclass
from enum import Enum, auto
from typing import Generator, Iterable, Optional, Union


class NumberClass(Enum):
    ROMAN_NUMERAL = auto()                   # 罗马数字
    LOWERCASE_ROMAN_NUMERAL = auto()         # 小写罗马数字
    CIRCLED_NUMBER = auto()                  # 带圆圈的数字
    PARENTHESIZED_CHINESE = auto()           # 括号中的汉字
    CIRCLED_CHINESE = auto()                 # 带圆圈的汉字
    BLACK_CIRCLED_NUMBER = auto()            # 黑色圆圈数字
    UNBOUNDED_NUMBER = auto()                # 无包围数字

class NumberStyle(Enum):
    ROMAN_NUMERAL = auto()                   # 罗马数字
    LOWERCASE_ROMAN_NUMERAL = auto()         # 小写罗马数字
    CIRCLED_NUMBER = auto()                  # 带圆圈的数字
    DOUBLE_CIRCLED_NUMBER = auto()           # 双圈数字
    CIRCLED_SANS_SERIF_NUMBER = auto()       # 带圆圈的无衬线数字
    BLACK_CIRCLED_SANS_SERIF_NUMBER = auto() # 黑色圆圈无衬线数字
    BLACK_CIRCLED_NUMBER = auto()            # 黑色圆圈数字
    PARENTHESIZED_CHINESE = auto()           # 括号中的汉字
    CIRCLED_CHINESE = auto()                 # 带圆圈的汉字
    FULL_WIDTH_NUMBER = auto()               # 全角数字
    MATHEMATICAL_BOLD_NUMBER = auto()        # 数学粗体数字
    ARTISTIC_BOLD_NUMBER = auto()            # 艺术粗体数字
    OUTLINED_BOLD_NUMBER = auto()            # 描边的粗体数字
    SUBSCRIPT_NUMBER = auto()                # 带角标的数字

@dataclass
class Mark:
    number: int
    char: str
    clazz: NumberClass
    style: NumberStyle

    def __str__(self) -> str:
        return self.char

    def __hash__(self):
        return hash((self.clazz, self.number))

    def __eq__(self, other) -> bool:
        if not isinstance(other, Mark):
            return False
        if self.clazz != other.clazz:
            return False
        if self.number != other.number:
            return False
        return True

def samples(number_style: NumberStyle, count: int) -> str:
    if count <= 1:
        raise ValueError("Count must be greater than 1")
    half_count = count // 2
    number_styles = _number_marks.styles.get(number_style, None)
    if number_styles is None:
        raise ValueError(f"Invalid number style: {number_style.name}")
    buffer = io.StringIO()
    for char in number_styles[:half_count]:
        buffer.write(char)
    buffer.write("...")
    for char in number_styles[-half_count:]:
        buffer.write(char)
    return buffer.getvalue()

def transform2mark(raw_char: str) -> Optional[Mark]:
    gotten = _number_marks.marks.get(raw_char, None)
    if gotten is None:
        return None
    return Mark(
            number=gotten.number,
            char=gotten.char,
            clazz=gotten.clazz,
            style=gotten.style
    )

def search_marks(text: str) -> Generator[Union[Mark, str], None, None]:
    for part in re.split(_number_marks.pattern, text):
        mark = transform2mark(part)
        if mark is None:
            yield part
        else:
            yield mark

class _NumberMarks:
    def __init__(self, styles: Iterable[tuple[NumberClass, NumberStyle, Iterable[tuple[int, str]]]]):
        self.marks: dict[str, Mark] = {}
        self.styles: dict[NumberStyle, list[str]] = {}
        for clazz, style, marks in styles:
            for number, mark in marks:
                self.marks[mark] = Mark(number, mark, clazz, style)
                self.styles[style] = [char for _, char in sorted(marks, key=lambda x: x[0])]

        self.pattern: re.Pattern = re.compile(
            r"([" + "".join(sorted(list(self.marks.keys()))) + r"])"
        )

# some of they are from https://tw.piliapp.com/symbol/number/
_number_marks = _NumberMarks((
    (NumberClass.ROMAN_NUMERAL, NumberStyle.ROMAN_NUMERAL, (
        (1, "Ⅰ"), (2, "Ⅱ"), (3, "Ⅲ"), (4, "Ⅳ"), (5, "Ⅴ"),
        (6, "Ⅵ"), (7, "Ⅶ"), (8, "Ⅷ"), (9, "Ⅸ"), (10, "Ⅹ"),
        (11, "Ⅺ"), (12, "Ⅻ"),
    )),
    (NumberClass.LOWERCASE_ROMAN_NUMERAL, NumberStyle.LOWERCASE_ROMAN_NUMERAL, (
        (1, "ⅰ"), (2, "ⅱ"), (3, "ⅲ"), (4, "ⅳ"), (5, "ⅴ"),
        (6, "ⅵ"), (7, "ⅶ"), (8, "ⅷ"), (9, "ⅸ"), (10, "ⅹ"),
        (11, "ⅺ"), (12, "ⅻ"),
    )),
    (NumberClass.CIRCLED_NUMBER, NumberStyle.CIRCLED_NUMBER, (
        (0, "⓪"), (1, "①"), (2, "②"), (3, "③"), (4, "④"),
        (5, "⑤"), (6, "⑥"), (7, "⑦"), (8, "⑧"), (9, "⑨"),
        (10, "⑩"), (11, "⑪"), (12, "⑫"), (13, "⑬"), (14, "⑭"),
        (15, "⑮"), (16, "⑯"), (17, "⑰"), (18, "⑱"), (19, "⑲"),
        (20, "⑳"), (21, "㉑"), (22, "㉒"), (23, "㉓"), (24, "㉔"),
        (25, "㉕"), (26, "㉖"), (27, "㉗"), (28, "㉘"), (29, "㉙"),
        (30, "㉚"), (31, "㉛"), (32, "㉜"), (33, "㉝"), (34, "㉞"),
        (35, "㉟"), (36, "㊱"), (37, "㊲"), (38, "㊳"), (39, "㊴"),
        (40, "㊵"), (41, "㊶"), (42, "㊷"), (43, "㊸"), (44, "㊹"),
        (45, "㊺"), (46, "㊻"), (47, "㊼"), (48, "㊽"), (49, "㊾"),
        (50, "㊿")
    )),
    (NumberClass.CIRCLED_NUMBER, NumberStyle.DOUBLE_CIRCLED_NUMBER, (
        (0, "⓵"), (1, "⓶"), (2, "⓷"), (3, "⓸"), (4, "⓹"),
        (5, "⓺"), (6, "⓻"), (7, "⓼"), (8, "⓽"), (9, "⓾"),
    )),
    (NumberClass.CIRCLED_NUMBER, NumberStyle.CIRCLED_SANS_SERIF_NUMBER, (
        (1, "➀"), (2, "➁"), (3, "➂"), (4, "➃"), (5, "➄"),
        (6, "➅"), (7, "➆"), (8, "➇"), (9, "➈"), (10, "➉"),
    )),
    (NumberClass.BLACK_CIRCLED_NUMBER, NumberStyle.BLACK_CIRCLED_SANS_SERIF_NUMBER, (
        (1, "➊"), (2, "➋"), (3, "➌"), (4, "➍"), (5, "➎"),
        (6, "➏"), (7, "➐"), (8, "➑"), (9, "➒"), (10, "➓"),
    )),
    (NumberClass.BLACK_CIRCLED_NUMBER, NumberStyle.BLACK_CIRCLED_NUMBER, (
        (0, "⓿"), (1, "❶"), (2, "❷"), (3, "❸"), (4, "❹"),
        (5, "❺"), (6, "❻"), (7, "❼"), (8, "❽"), (9, "❾"),
        (10, "❿"), (11, "⓫"), (12, "⓬"), (13, "⓭"), (14, "⓮"),
        (15, "⓯"), (16, "⓰"), (17, "⓱"), (18, "⓲"), (19, "⓳"),
        (20, "⓴"),
    )),
    (NumberClass.PARENTHESIZED_CHINESE, NumberStyle.PARENTHESIZED_CHINESE, (
        (1, "㈠"), (2, "㈡"), (3, "㈢"), (4, "㈣"), (5, "㈤"),
        (6, "㈥"), (7, "㈦"), (8, "㈧"), (9, "㈨"), (10, "㈩"),
    )),
    (NumberClass.CIRCLED_CHINESE, NumberStyle.CIRCLED_CHINESE, (
        (1, "㊀"), (2, "㊁"), (3, "㊂"), (4, "㊃"), (5, "㊄"),
        (6, "㊅"), (7, "㊆"), (8, "㊇"), (9, "㊈"), (10, "㊉"),
    )),
    (NumberClass.UNBOUNDED_NUMBER, NumberStyle.FULL_WIDTH_NUMBER, (
        (0, "０"), (1, "１"), (2, "２"), (3, "３"), (4, "４"),
        (5, "５"), (6, "６"), (7, "７"), (8, "８"), (9, "９"),
    )),
    (NumberClass.UNBOUNDED_NUMBER, NumberStyle.MATHEMATICAL_BOLD_NUMBER, (
        (0, "𝟬"), (1, "𝟭"), (2, "𝟮"), (3, "𝟯"), (4, "𝟰"),
        (5, "𝟱"), (6, "𝟲"), (7, "𝟳"), (8, "𝟴"), (9, "𝟵"),
    )),
    (NumberClass.UNBOUNDED_NUMBER, NumberStyle.ARTISTIC_BOLD_NUMBER, (
        (0, "𝟎"), (1, "𝟏"), (2, "𝟐"), (3, "𝟑"), (4, "𝟒"),
        (5, "𝟓"), (6, "𝟔"), (7, "𝟕"), (8, "𝟖"), (9, "𝟗"),
    )),
    (NumberClass.UNBOUNDED_NUMBER, NumberStyle.OUTLINED_BOLD_NUMBER, (
        (0, "𝟘"), (1, "𝟙"), (2, "𝟚"), (3, "𝟛"), (4, "𝟜"),
        (5, "𝟝"), (6, "𝟞"), (7, "𝟟"), (8, "𝟠"), (9, "𝟡"),
    )),
    (NumberClass.UNBOUNDED_NUMBER, NumberStyle.SUBSCRIPT_NUMBER, (
        (0, "🄁"), (1, "🄂"), (2, "🄃"), (3, "🄄"), (4, "🄅"),
        (5, "🄆"), (6, "🄇"), (7, "🄈"), (8, "🄉"), (9, "🄊"),
    )),
))
