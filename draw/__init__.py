from datetime import datetime
import math
from typing import List, Optional

from PIL import Image, ImageDraw
from hoshino.modules.priconne import chara
from ..utils.tool import long_id_to_short, outp_b64

from ..constants import FONT_PATH, ArenaRecordType
from .util import (
    TalentType,
    im_head,
    im_body,
    im_bottom,
    font,
    thumb_up_a,
    thumb_down_a,
    big_font,
    matrix_palette,
    rounded_rect,
    matrix_im,
)
from ..model import ArenaQueryRecord
from math import ceil
from ..database.sqla import pcr_sqla

BODY_HEIGHT = 139


def generate_canvas(entries_num: int, per_entry_height: int = 69) -> Image.Image:
    """根据需要动态生成画布：
    - 使用 im_head、im_body、im_bottom 的实际高度
    - 按 `per_entry_height` 计算所需的条目高度
    - 对最后一块 body 进行裁剪以避免出现多余空隙
    """

    total_entries_h = entries_num * per_entry_height

    full_body_parts = total_entries_h // im_body.height
    remainder = total_entries_h % im_body.height

    total_body_h = full_body_parts * im_body.height + remainder
    total_height = im_head.height + total_body_h + im_bottom.height

    im = Image.new("RGBA", (im_head.width, total_height), (255, 255, 255, 255))
    im.paste(im_head, (0, 0))

    y = im_head.height
    for _ in range(full_body_parts):
        im.paste(im_body, (0, y))
        y += im_body.height

    if remainder:
        # 裁剪 body 的顶部区域以填充剩余高度，避免整片 body 导致底部空隙
        cropped = im_body.crop((0, 0, im_body.width, remainder))
        im.paste(cropped, (0, y))
        y += remainder

    im.paste(im_bottom, (0, y))
    return im


async def draw_units(
    im: Image.Image,
    units: List[int],
    start_x: int,
    start_y: int,
    icon_size: int = 64,
    gap: int = 5,
    vertical: bool = False,
):
    for j, c in enumerate(pcr_sqla.deck_sort_unit(units)[::-1]):
        x1 = start_x + (0 if vertical else j * (icon_size + gap))
        y1 = start_y + (j * (icon_size + gap) if vertical else 0)
        char = chara.fromid(long_id_to_short(c))
        icon = await char.render_icon(icon_size)
        im.paste(icon, (x1, y1, x1 + icon_size, y1 + icon_size), icon)
        if talent := pcr_sqla.get_unit_talent(c):
            talent_icon = TalentType.get(talent).icon.resize(
                (math.ceil(icon_size / 3), math.ceil(icon_size / 3))
            )
            im.paste(
                talent_icon,
                (
                    x1 + icon_size - talent_icon.width,
                    y1 + icon_size - talent_icon.height,
                ),
                talent_icon,
            )


async def render_atk_def_teams(
    results: List[ArenaQueryRecord], border_pix=30
) -> Image.Image:
    """
    entries = [ {'atk': [int], 'up': int, 'down': int } ]
    """
    if results[-1].type == ArenaRecordType.placehodlder:
        results = results[:-1]
    n = len(results)
    icon_size = 64
    small_icon_size = 32
    _im = generate_canvas(n)
    # font = ImageFont.truetype(str(working_dir / 'resources' / 'wqy.ttf'), 14)
    draw = ImageDraw.Draw(_im)
    await pcr_sqla.get_all_units()
    for i, result in enumerate(results):
        if result.type == ArenaRecordType.placehodlder:
            continue

        y1 = (i * (icon_size + 5)) + border_pix
        await draw_units(_im, result.solution.atk, border_pix, y1, icon_size, gap=0)

        x1 = 5 * icon_size + 10
        if result.type in (
            ArenaRecordType.pcrfans,
            ArenaRecordType.pcrfans_cache,
            ArenaRecordType.pcrfans_old_cache,
        ):
            x2 = x1 + 16
            _im.paste(
                thumb_up_a,
                (x1 + border_pix, y1 + 12, x2 + border_pix, y1 + 28),
                thumb_up_a,
            )
            _im.paste(
                thumb_down_a,
                (x1 + border_pix, y1 + 39, x2 + border_pix, y1 + 55),
                thumb_down_a,
            )
            draw.text(
                (x1 + 25 + border_pix, y1 + 10),
                f"{result.solution.up}",
                (0, 0, 0, 255),
                font,
            )
            draw.text(
                (x1 + 25 + border_pix, y1 + 35),
                f"{result.solution.down}",
                (0, 0, 0, 255),
                font,
            )

        elif result.type in (
            ArenaRecordType.pcrfans_approximate,
            ArenaRecordType.mzq_approximate,
        ):
            orginal, replace = list(result.replace.items())[0]
            draw.text((x1 + 22, y1 - 3), "近似解", (0, 0, 0, 255), font)
            chara_1 = chara.fromid(long_id_to_short(orginal))
            icon_1 = await chara_1.render_icon(small_icon_size)
            _im.paste(icon_1, (x1 + 22, y1 + 26), icon_1)
            draw.text((x1 + 55, y1 + 32), "→", (0, 0, 0, 255), font)

            chara_2 = chara.fromid(long_id_to_short(replace))
            icon_2 = await chara_2.render_icon(small_icon_size)
            _im.paste(icon_2, (x1 + 72, y1 + 26), icon_2)
        elif result.type in (
            ArenaRecordType.pcrfans_often_used,
            ArenaRecordType.mzq_often_used,
        ):
            draw.text((x1 + 22, y1 + 22), "高频解", (0, 0, 0, 255), font)

        if result.type in (
            ArenaRecordType.mzq,
            ArenaRecordType.mzq_approximate,
            ArenaRecordType.mzq_often_used,
        ):
            draw.text((x1 + 122, y1 + 2), "模拟对战解", (0, 0, 0, 255), font)

            # 显示胜率和统计信息
            win_rate = result.solution.win_rate
            stats_str = f"胜{result.solution.win_count}/负{result.solution.lose_count}/超时{result.solution.timeout_count}({win_rate:.0%})"
            draw.text(
                (x1 + 122, y1 + 20),
                stats_str,
                (0, 0, 0, 255),
                font,
            )

            # 显示战斗时长
            seconds = result.solution.cost_time
            time_str = f"{seconds:.1f}秒"
            draw.text(
                (x1 + 122, y1 + 38),
                f"时间：{time_str}",
                (0, 0, 0, 255),
                font,
            )

            time_str = datetime.fromtimestamp(result.solution.timestamp).strftime(
                "%Y-%m-%d"
            )
            draw.text(
                (x1 + 122, y1 + 56),
                f"查询时间：{time_str}",
                (0, 0, 0, 255),
                font,
            )

    return outp_b64(_im)


async def render_matrix(
    atk_teams: List[List[int]],
    def_teams: List[List[int]],
    matrix: List[List[Optional[ArenaQueryRecord]]],
) -> str:
    """渲染竞技场矩阵图：行=进攻队，列=防守队，单元格为胜率。"""
    n_atk = len(atk_teams)

    icon_size = 42
    gap = 5
    corner = icon_size * 5 + gap * 6
    cell = 94

    n_def = len(def_teams)
    width = corner + n_def * cell + 16
    height = corner + n_atk * cell + 16

    img = Image.new("RGB", (width, height), (241, 245, 249))
    draw = ImageDraw.Draw(img)
    card_box = (0, 0, width, height)
    rounded_rect(draw, card_box, 16, (255, 255, 255), (226, 232, 240), 1)

    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((16, 20), "竞技场模拟结果", fill=(100, 116, 139), font=font)
    draw.text((16, 42), f"模拟时间：{time_str}", fill=(100, 116, 139), font=font)
    draw.text(
        (16, 64),
        f"进攻 {n_atk}队 x 防守 {n_def}队, 共 {n_atk * n_def} 组模拟",
        fill=(100, 116, 139),
        font=font,
    )

    img.paste(matrix_im, (60, 110), matrix_im)

    origin_x = 12
    origin_y = 12
    band_def = (
        origin_x + corner,
        origin_y,
        origin_x + corner + n_def * cell,
        origin_y + corner,
    )
    rounded_rect(draw, band_def, 10, (252, 252, 253), (241, 245, 249), 1)
    for j, t in enumerate(def_teams):
        col_x0 = origin_x + corner + j * cell
        stack_h = 5 * icon_size + 4 * gap
        y0 = origin_y + (corner - stack_h) // 2
        await draw_units(
            img,
            list(t),
            col_x0 + (cell - icon_size) // 2,
            y0,
            icon_size,
            gap,
            vertical=True,
        )

    band_atk = (
        origin_x,
        origin_y + corner,
        origin_x + corner,
        origin_y + corner + n_atk * cell,
    )
    rounded_rect(draw, band_atk, 10, (252, 252, 253), (241, 245, 249), 1)
    for i, t in enumerate(atk_teams):
        row_y0 = origin_y + corner + i * cell
        row_w = 5 * icon_size + 4 * gap
        x0 = origin_x + (corner - row_w) // 2
        await draw_units(
            img,
            list(t),
            x0,
            row_y0 + (cell - icon_size) // 2,
            icon_size,
            gap,
        )

    mx0 = origin_x + corner
    my0 = origin_y + corner
    inset = 5
    for i, row in enumerate(matrix):
        for j, rec in enumerate(row):
            x0 = mx0 + j * cell + inset
            y0 = my0 + i * cell + inset
            x1 = mx0 + (j + 1) * cell - inset
            y1 = my0 + (i + 1) * cell - inset
            total = 0
            wr = 0.0
            if rec and rec.solution:
                total = (
                    rec.solution.win_count
                    + rec.solution.lose_count
                    + rec.solution.timeout_count
                )
                if total > 0:
                    wr = rec.solution.win_rate
            if total > 0:
                fill, tcol = matrix_palette(wr)
                text = f"{wr:.0%}"
            else:
                fill = (241, 245, 249)
                tcol = (100, 116, 139)
                text = "ERROR"
            rounded_rect(draw, (x0, y0, x1, y1), 12, fill, (226, 232, 240), 1)
            bbox = draw.textbbox((0, 0), text, font=big_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            cx = (x0 + x1 - tw) // 2 - bbox[0]
            cy = (y0 + y1 - th) // 2 - bbox[1]
            draw.text((cx, cy), text, fill=tcol, font=big_font)

    return outp_b64(img)
