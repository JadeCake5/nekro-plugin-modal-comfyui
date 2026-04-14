"""
图片解密模块

与 comfyui-encrypt-image (viyiviyi/comfyui-encrypt-image) 项目的加密算法对应。
支持 pixel_shuffle (v1) 和 pixel_shuffle_2 (v2) 两种解密方式。
"""

import hashlib
import numpy as np
from PIL import Image


def get_range(input: str, offset: int, range_len: int = 4) -> str:
    """从输入字符串中获取指定范围的内容（循环使用）"""
    offset = offset % len(input)
    return (input * 2)[offset:offset + range_len]


def get_sha256(input: str) -> str:
    """计算 SHA256 哈希"""
    hash_object = hashlib.sha256()
    hash_object.update(input.encode('utf-8'))
    return hash_object.hexdigest()


def shuffle_arr(arr, key):
    """
    shuffle_arr - 与 comfyui-encrypt-image 项目保持一致
    关键：使用 key_offset 递增，而不是直接用 i
    """
    sha_key = get_sha256(key)
    key_len = len(sha_key)
    arr_len = len(arr)
    key_offset = 0
    for i in range(arr_len):
        to_index = int(get_range(sha_key, key_offset, range_len=8), 16) % (arr_len - i)
        key_offset += 1
        if key_offset >= key_len:
            key_offset = 0
        arr[i], arr[to_index] = arr[to_index], arr[i]
    return arr


def dencrypt_image(image: Image.Image, psw):
    """v1 解密 - 原地修改像素"""
    width = image.width
    height = image.height
    x_arr = [i for i in range(width)]
    shuffle_arr(x_arr, psw)
    y_arr = [i for i in range(height)]
    shuffle_arr(y_arr, get_sha256(psw))
    pixels = image.load()
    for x in range(width - 1, -1, -1):
        _x = x_arr[x]
        for y in range(height - 1, -1, -1):
            _y = y_arr[y]
            pixels[x, y], pixels[_x, _y] = pixels[_x, _y], pixels[x, y]
    return image


def dencrypt_image_v2(image: Image.Image, psw):
    """v2 解密 - 使用 numpy 数组（性能更好）"""
    width = image.width
    height = image.height
    x_arr = [i for i in range(width)]
    shuffle_arr(x_arr, psw)
    y_arr = [i for i in range(height)]
    shuffle_arr(y_arr, get_sha256(psw))
    pixel_array = np.array(image)

    pixel_array = np.transpose(pixel_array, axes=(1, 0, 2))
    for x in range(width - 1, -1, -1):
        _x = x_arr[x]
        temp = pixel_array[x].copy()
        pixel_array[x] = pixel_array[_x]
        pixel_array[_x] = temp
    pixel_array = np.transpose(pixel_array, axes=(1, 0, 2))
    for y in range(height - 1, -1, -1):
        _y = y_arr[y]
        temp = pixel_array[y].copy()
        pixel_array[y] = pixel_array[_y]
        pixel_array[_y] = temp

    image.paste(Image.fromarray(pixel_array))
    return image


def get_encrypt_password(password: str) -> str:
    """
    计算存储用的密码哈希（用于验证 EncryptPwdSha）
    公式: get_sha256(get_sha256(password) + "Encrypt")
    """
    return get_sha256(get_sha256(password) + "Encrypt")


def get_decrypt_password(password: str) -> str:
    """获取解密用的密码（直接对原始密码做 SHA256）"""
    return get_sha256(password)


def decrypt_process(image: Image.Image, password: str) -> Image.Image:
    """
    根据图片元数据中的 Encrypt 字段自动选择解密方法

    Args:
        image: 加密的 PIL Image 对象
        password: 原始密码

    Returns:
        解密后的 PIL Image 对象
    """
    pnginfo = image.info or {}
    decrypt_psw = get_decrypt_password(password)

    if 'Encrypt' in pnginfo:
        method = pnginfo["Encrypt"]
        if method == 'pixel_shuffle':
            return dencrypt_image(image, decrypt_psw)
        elif method == 'pixel_shuffle_2':
            return dencrypt_image_v2(image, decrypt_psw)

    # 默认使用 v2
    return dencrypt_image_v2(image, decrypt_psw)
