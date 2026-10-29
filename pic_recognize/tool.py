import numpy as np

from PIL import Image


async def crop_image(img, border):
    """
    :param img: 待裁剪图片 PIL.Image
    :param border: 裁剪范围 [x, y, w, h]
    :return 裁剪后图像 PIL.Image
    """
    x, y, w, h = border
    img = np.array(img)
    img = img[y + 2: y + h - 2, x + 2: x + w - 2]
    return Image.fromarray(img)


def get_hash_arr(image: Image.Image, hash_size=16):
    image_lists = list(
        image.resize((hash_size + 1, hash_size),
                     resample=Image.Resampling.LANCZOS)
        .convert("L")
        .getdata()
    )
    assert len(image_lists) == 17 * 16, "size error"
    m, n = 0, 17
    hash_list = []
    for _ in range(16):
        slc = slice(m, n)
        image_slc = image_lists[slc]
        hash_list.append(
            [
                1 if image_lists[index - 1] > val else 0
                for index, val in enumerate(image_slc)
            ][1:]
        )
        m += 17
        n += 17
    return np.array(hash_list)


def calc_distance(arr1: np.ndarray, arr2: np.ndarray) -> int:
    """计算两张图片的感知哈希距离"""
    return sum(sum(abs(arr1 - arr2)))
