import numpy as np
from hoshino import R

from ..constants import DATA_PATH, UNIT_PATTERN
import contextlib
from pathlib import Path
import re
from ..database.sqla import pcr_sqla
from PIL import Image
from .tool import get_hash_arr

DIC_PATH = DATA_PATH / "dic.npy"

dic_data = None
data_processed = None


def load_dic():
    global dic_data
    dic_data = np.load(DIC_PATH, allow_pickle=True).item() if DIC_PATH.is_file() else {}


def load_data_processed():
    global data_processed
    processed = {
        uid: get_hash_arr(Image.fromarray(dic_data[uid][25:96, 8:97, :]))
        for uid in dic_data
    }
    if data_processed is None:
        data_processed = processed
    else:
        # extract_position 持有该字典的引用，更新时需要同步原对象。
        data_processed.clear()
        data_processed.update(processed)


load_dic()
load_data_processed()


async def update_dic():
    nowpath = Path(R.get("img/priconne/unit/").path)
    dic = {}
    icon_list = []
    units = list(await pcr_sqla.get_all_units())
    units = [unit // 100 for unit in units]
    for file in nowpath.iterdir():
        with contextlib.suppress(Exception):
            ret = re.match(UNIT_PATTERN, file.name)
            icon_id = int(ret[1])
            if (icon_id // 100 in units) or (icon_id == 100031):
                # 但此处我们需要识别问号（pjjc用），因此设置为[1000, 1900)
                icon_list.append([file, icon_id])
    msg = [f"共检测到{len(icon_list)}个pcr头像"]
    cnt_success = 0
    for file, icon_id in icon_list:
        try:
            img = Image.open(str(nowpath / file))
            img = img.convert("RGB")
            img = img.resize((128, 128))
            dic[icon_id] = np.array(img)
            cnt_success += 1
        except Exception as e:
            msg.append(f"Warning. 头像{icon_id}加入识别库失败：{e}")
    np.save(DIC_PATH, dic)
    load_dic()
    load_data_processed()
    if cnt_success:
        msg.append(f"Succeed. 更新成功。共收录{cnt_success}个头像进入识别库")
    return "\n".join(msg)
