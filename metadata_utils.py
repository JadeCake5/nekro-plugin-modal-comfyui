"""
工作流元数据去除模块

移除 ComfyUI 图片中的工作流元数据（workflow, prompt, parameters 等），
以及加密相关的元数据（Encrypt, EncryptPwdSha）。
"""

from io import BytesIO
from PIL import Image, PngImagePlugin


def remove_workflow_metadata(image_source) -> bytes:
    """
    移除图片中的工作流元数据，返回纯净的 PNG 字节

    Args:
        image_source: 可以是 Path 对象、Image 对象或 PNG 字节

    Returns:
        bytes: 去除元数据后的 PNG 图片字节
    """
    if isinstance(image_source, bytes):
        img = Image.open(BytesIO(image_source))
        should_close = True
    elif isinstance(image_source, Image.Image):
        img = image_source
        should_close = False
    else:
        img = Image.open(image_source)
        should_close = True

    try:
        original_metadata = dict(img.info) if hasattr(img, 'info') else {}

        # 工作流相关的键名（ComfyUI 常用）
        workflow_keys = ['workflow', 'prompt', 'parameters', 'comment']

        # 创建新的 PngInfo，只保留非工作流、非加密数据
        new_pnginfo = PngImagePlugin.PngInfo()
        for key, value in original_metadata.items():
            if not any(wk in key.lower() for wk in workflow_keys):
                if key.lower() not in ['encrypt', 'encryptpwdsha']:
                    new_pnginfo.add_text(key, str(value))

        output = BytesIO()
        img.save(output, format='PNG', pnginfo=new_pnginfo)
        return output.getvalue()
    finally:
        if should_close:
            img.close()
