from typing import Tuple
import cv2
import numpy as np
from PIL import Image, ImageColor, ImageDraw


from ..utils.tool import outp_b64, short_id_to_long
from .tool import crop_image, calc_distance
from hoshino.modules.priconne import chara
from .dic import data_processed, get_hash_arr


def identify_square_regions(img: Image.Image, mode: int):
    """
    :param img: 传入的待识别的原图片 PIL格式
    :param mode: mode=1：返回图片中最大的长方形区域，以及该区域的定位点 [PIL.Image, [x, y, w, h]] ; mode=2: 返回两个列表，列表中每个元素为正方形区域在原图的[x, y, w, h]。第一个列表为聚类结果，第二个列表为排除结果。若无正方形区域，返回[], []。
    """
    im_grey = img.convert("L")
    totArea = (im_grey.size)[0] * (im_grey.size)[1]
    im_grey = im_grey.point(
        lambda x: 255 if x > 210 else 0
    )  # 没有用自带的二值化。考虑修改，使用更合适的函数。
    thresh = np.array(im_grey)

    # cv2.findContours. opencv3版本会返回3个值，opencv2和4只返回后两个值
    # img2, contours, hier = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours, hier = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )  # 获取轮廓
    img2 = thresh

    lis = []
    icon = []  # 每个元素为：[边长，[矩阵左上点坐标，矩阵宽高]]
    # icon_area = {}  # key为边长 value为个数
    for i in range(len(contours)):
        area = cv2.contourArea(contours[i])  # 计算contour包围的像素点个数
        lis.append(area)
        if area > 500 and mode == 2:
            x, y, w, h = cv2.boundingRect(contours[i])  # 获取contour的aabb包围盒
            if w / h > 0.95 and w / h < 1.05:  # 近似正方形
                are = (w + h) // 2
                areaRatio = are * are / totArea * 100  # 获取该范围占整个输入图像的占比
                # print(f"{areaRatio:2f}%")
                if areaRatio >= 0.5:  # 过滤占比小于0.5%的正方形（可能为文字）
                    icon.append([are, [x, y, w, h]])
                    # icon_area[are] = icon_area.setdefault(are, 0) + 1

    # print()
    if mode == 1:
        i = lis.index(max(lis))
        x, y, w, h = cv2.boundingRect(contours[i])
        # cv2.rectangle(img2, (x, y), (x + w, y + h), (153, 153, 0), 5)
        img3 = img2[y + 2 : y + h - 2, x + 2 : x + w - 2]
        img4 = Image.fromarray(img3)
        return img4, [x, y, w, h]
    if mode == 2:
        if not icon:
            return [], []

        # 对边长作简易聚类分析
        kinds = {}  # 边长: [[],[],[],...,[]]
        for i in icon:
            sidelen = i[0]
            category = -1
            for kind in kinds:
                ratio = sidelen / kind
                if ratio > 0.9 and ratio < 1.1:  # 将边长相差10%以内作为一类
                    category = kind
                    kinds[kind].append(i[1])
                    break
            if category == -1:
                kinds[sidelen] = [i[1]]

        def clusterWeight(x):
            sidelen = x[0]
            val = len(x[1])
            if val == 5:  # 该类有5个元素，优先返回。第二关键字为边长（从大到小）。
                return 5000000 + sidelen
            return 1000000 + sidelen if val % 5 == 0 else val * 10000 + sidelen

        kinds = sorted(kinds.items(), key=clusterWeight, reverse=True)
        kind = kinds[0]  # (边长, [[],[]])
        if len(kind[1]) % 5 == 0:  # 存在某一类，其元素个数为5的倍数，返回该类
            otherborder = []
            for x in range(1, len(kinds)):
                otherborder += kinds[x][1]
            return kind[1], otherborder
        else:
            # 否则返回所有找到的正方形区域，由后续程序进一步判断
            return [x[1] for x in icon], []


def recognize_unit(img2: Image.Image) -> tuple[int, int, str, int]:
    img2 = img2.convert("RGB").resize((128, 128), Image.Resampling.LANCZOS)
    img3 = np.array(img2)
    img4 = img3[25:96, 8:97, :]
    img4 = Image.fromarray(img4)
    dic = {}

    for uid in data_processed:
        dic[uid] = calc_distance(data_processed[uid], get_hash_arr(img4))

    lis = list(sorted(dic.items(), key=lambda x: abs(x[1])))

    similarity = int(lis[0][1])
    if similarity > 90:  # 没一个相似的
        return 0, 0, "Unknown", 100 - similarity
    uid_6 = int(lis[0][0])
    uid = uid_6 // 100

    return uid_6, uid, chara.fromid(uid).name, 100 - similarity


async def extract_position(img: Image.Image) -> Tuple[list, str]:
    """
    :param img: 待识别图片 PIL.Image
    :return 识别出的阵容的坐标, 识别出的阵容角色字符串 [[第1队第1个角色(int), 1-2, ..., 1-5], [2-1, ..., 2-5], [3-1, ..., 3-5]], str；若识别失败，返回[], ""
    """
    if not data_processed:
        raise ValueError("识别卡池尚未生成，请先发送“竞技场更新卡池”")
    img = img.convert("RGBA")
    im_grey = img
    actual_img = img
    actual_x = 0
    actual_y = 0
    nowcolor = 0
    outpImg = Image.new(
        mode="RGBA",
        size=img.size,
        color=ImageColor.getrgb(f"rgb({nowcolor},{nowcolor},{nowcolor})"),
    )
    outpImgText = Image.new("RGBA", img.size, (0, 0, 0, 0))
    outpImgTextDraw = ImageDraw.Draw(outpImgText)

    cnt = 0
    while cnt <= 6:
        bo = False
        cnt += 1
        # 获取当前图像中的正方形区域
        border, otherborder = identify_square_regions(im_grey, 2)
        if len(border) == 0:  # 如果莫得 说明需要翻转图像的黑白
            bo = True
        else:
            # print(f'cnt={cnt} border={border}') # test
            # 将正方形区域按照行列分组
            def highlight(
                rec, color="red"
            ):  # 识别成功red 被其它代码排除的识别项blue 超过五列未识别的green 识别不出角色的black 识别出是100031的yellow
                x, y, w, h = rec
                cropped = img.crop([x + 2, y + 2, x + w - 2, y + h - 2])
                outpImgText.paste(
                    cropped,
                    (
                        actual_x + x + 2,
                        actual_y + y + 2,
                        actual_x + x + w - 2,
                        actual_y + y + h - 2,
                    ),
                )
                outpImgTextDraw.rectangle(
                    (actual_x + x, actual_y + y, actual_x + x + w, actual_y + y + h),
                    fill=None,
                    outline=color,
                    width=4,
                )

            for i in otherborder:
                highlight(i, "blue")
            if (
                len(border) < 4
            ):  # 由5改为4 是为了日后准备加入残缺队伍查询（通过无api版本）
                for i in border:
                    highlight(i, "blue")
            else:
                recs = border
                recs = {tuple(rec) for rec in recs}

                def split_last_col_recs(recs):
                    recs = sorted(recs, key=lambda x: x[0], reverse=True)
                    last_col_recs = [
                        rec for rec in recs if abs(rec[0] - recs[0][0]) < recs[0][2] / 2
                    ]
                    last_col_recs = sorted(last_col_recs, key=lambda x: x[1])
                    return list(set(recs) - set(last_col_recs)), last_col_recs

                _, last_col_recs = split_last_col_recs(recs)  # 先找出最右侧的一列有几行
                row_cnt = len(last_col_recs)

                arr = [[None for __ in range(5)] for _ in range(row_cnt)]
                arr_id = [[] for _ in range(row_cnt)]
                arr_id_6 = [[0 for __ in range(5)] for _ in range(row_cnt)]
                last_col_recs_xpos = [
                    rec[1] for rec in last_col_recs
                ]  # 以最右一列的坐标为基准

                for col_index in range(5):  # 从右往左一列一列掰，最多拿五列
                    recs, last_col_recs = split_last_col_recs(recs)
                    if len(last_col_recs) == 0:
                        break
                    for rec in last_col_recs:
                        # 看看rec能不能被识别出来
                        x, y, w, h = rec
                        cropped = img.crop([x + 2, y + 2, x + w - 2, y + h - 2])
                        uid_6, unit_id, unit_name, similarity = recognize_unit(cropped)
                        # print(uid_6, unit_id, unit_name, similarity)  # 0 0 Unknown -1~-5
                        if unit_id == 0:
                            highlight(rec, "black")
                        else:
                            highlight(rec, "red" if unit_id != 1000 else "yellow")
                            most_near_row = 0
                            for row_index in range(1, len(arr)):
                                if abs(last_col_recs_xpos[row_index] - rec[1]) < abs(
                                    last_col_recs_xpos[most_near_row] - rec[1]
                                ):
                                    most_near_row = row_index
                            if arr[most_near_row][col_index] is None or abs(
                                last_col_recs_xpos[most_near_row]
                                - arr[most_near_row][col_index][1]
                            ) > abs(last_col_recs_xpos[most_near_row] - rec[1]):
                                arr[most_near_row][col_index] = rec
                                arr_id[most_near_row].append(short_id_to_long(unit_id))
                                arr_id_6[most_near_row][col_index] = uid_6

                for rec in recs:
                    highlight(rec, "green")

                # 创建一个 rowcnt行 5列 的画布，行间及四周留16px空隙，每行中的每列分为上下两个头像：截出来的和通过识别的id render出来的（均为64*64)。头像间隙0px。
                icon_size = 64
                compare_img = Image.new(
                    "RGBA",
                    (
                        icon_size * 5 + 16 * 2,
                        icon_size * 2 * row_cnt + 16 * (row_cnt + 1),
                    ),
                    (255, 255, 255, 255),
                )

                for row_index in range(row_cnt):
                    none_cnt = arr[row_index].count(None)
                    if none_cnt >= 2:  # 不允许1-3个角色查询 不渲染
                        arr_id[row_index] = []
                        continue
                    for col_index in range(5):
                        if arr[row_index][4 - col_index] is None:
                            continue
                        pos_x = 16 + icon_size * col_index
                        pos_y = 16 * (row_index + 1) + icon_size * 2 * row_index
                        x, y, w, h = arr[row_index][4 - col_index]
                        cropped = img.crop([x + 2, y + 2, x + w - 2, y + h - 2]).resize(
                            (64, 64), Image.Resampling.LANCZOS
                        )
                        compare_img.paste(
                            cropped, (pos_x, pos_y), cropped
                        )  # 要不要加cropped
                        c = chara.fromid(
                            arr_id_6[row_index][4 - col_index] // 100,
                            arr_id_6[row_index][4 - col_index] % 100 // 10,
                        )
                        icon = await c.render_icon(icon_size)
                        compare_img.paste(icon, (pos_x, pos_y + 64), icon)

                outpImg = Image.blend(outpImg, actual_img, 0.2)
                outpImg.alpha_composite(outpImgText)
                ratio = max(1, max((outpImg.size)[0], (outpImg.size)[1]) / 500)
                outpImg = outpImg.resize(
                    (int((outpImg.size)[0] / ratio), int((outpImg.size)[1] / ratio)),
                    Image.Resampling.LANCZOS,
                )

                return arr_id, f"{outp_b64(outpImg)}\n{outp_b64(compare_img)}"

        # 获取图片中最大的长方形区域
        im_grey, border = identify_square_regions(im_grey, 1)
        if cnt == 1 or bo:  # 如果是第一次裁剪，或者识别不到正方形区域，反色
            im_grey = im_grey.point(lambda x: 0 if x > 128 else 255)
        img = await crop_image(img, border)  # 将原始img也裁剪，和im_grey同步
        actual_x += border[0]
        actual_y += border[1]

        nowcolor = (nowcolor + 60) % 300
        outpImg.paste(
            ImageColor.getrgb(f"rgb({nowcolor},{nowcolor},{nowcolor})"),
            (actual_x, actual_y, actual_x + border[2], actual_y + border[3]),
        )

        # outpImg.show()  # test

    return [], ""
