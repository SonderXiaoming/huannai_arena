from enum import Enum
from typing import Optional, Tuple
from hoshino import R
from hoshino.typing import *
from PIL import Image, ImageDraw, ImageFont
from loguru import logger
from ..constants import IMG_PATH, FONT_PATH

thumb_up_i = (
    R.img("priconne/gadget/thumb-up-i.png")
    .open()
    .resize((16, 16), Image.Resampling.LANCZOS)
)
thumb_up_a = (
    R.img("priconne/gadget/thumb-up-a.png")
    .open()
    .resize((16, 16), Image.Resampling.LANCZOS)
)
thumb_down_i = (
    R.img("priconne/gadget/thumb-down-i.png")
    .open()
    .resize((16, 16), Image.Resampling.LANCZOS)
)
thumb_down_a = (
    R.img("priconne/gadget/thumb-down-a.png")
    .open()
    .resize((16, 16), Image.Resampling.LANCZOS)
)
im_head = Image.open(str(IMG_PATH / "head.png"))
im_body = Image.open(str(IMG_PATH / "body.png"))
im_bottom = Image.open(str(IMG_PATH / "bottom.png"))
matrix_im = Image.open(str(IMG_PATH / "matrix.png")).resize((128, 128))
font = ImageFont.truetype(str(FONT_PATH / "wqy.ttf"), 14)
big_font = ImageFont.truetype(str(FONT_PATH / "wqy.ttf"), 30)


class TalentType(Enum):
    fire = "火"
    water = "水"
    wind = "风"
    light = "光"
    dark = "暗"

    icon_dict = {
        "火": Image.open(str(IMG_PATH / "talent" / "fire.png")).resize(
            (22, 22), Image.Resampling.LANCZOS
        ),
        "水": Image.open(str(IMG_PATH / "talent" / "water.png")).resize(
            (22, 22), Image.Resampling.LANCZOS
        ),
        "风": Image.open(str(IMG_PATH / "talent" / "wind.png")).resize(
            (22, 22), Image.Resampling.LANCZOS
        ),
        "光": Image.open(str(IMG_PATH / "talent" / "light.png")).resize(
            (22, 22), Image.Resampling.LANCZOS
        ),
        "暗": Image.open(str(IMG_PATH / "talent" / "dark.png")).resize(
            (22, 22), Image.Resampling.LANCZOS
        ),
    }

    @property
    def name(self) -> str:
        return self.value

    @property
    def index(self) -> int:
        if self == TalentType.fire:
            return 1
        elif self == TalentType.water:
            return 2
        elif self == TalentType.wind:
            return 3
        elif self == TalentType.light:
            return 4
        elif self == TalentType.dark:
            return 5
        else:
            return 0

    @property
    def icon(self) -> Image.Image:
        return self.icon_dict.value.get(self.name)

    @classmethod
    def get(cls, index: int) -> "TalentType":
        if index == 1:
            return cls.fire
        elif index == 2:
            return cls.water
        elif index == 3:
            return cls.wind
        elif index == 4:
            return cls.light
        elif index == 5:
            return cls.dark
        else:
            return None


def matrix_palette(p: float) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """(背景填充色, 文字色)"""
    if p >= 0.8:
        return (209, 250, 229), (20, 83, 45)
    if p >= 0.5:
        return (254, 243, 199), (146, 64, 14)
    return (254, 215, 215), (127, 29, 29)


def rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int,
    fill: Tuple[int, int, int],
    outline: Optional[Tuple[int, int, int]] = None,
    width: int = 1,
) -> None:
    try:
        draw.rounded_rectangle(
            xy, radius=radius, fill=fill, outline=outline, width=width
        )
    except AttributeError:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)
