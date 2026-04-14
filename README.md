# Modal ComfyUI 绘图插件

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Nekro Agent](https://img.shields.io/badge/Nekro_Agent-Plugin-green.svg)](https://github.com/KroMiose/nekro-agent)

通过 Modal 云端 ComfyUI 的 Generate API 生成动漫风格图片的 Nekro Agent 第三方插件。

## 主要功能

- **云端绘图**: 一次 POST 请求调用 Modal ComfyUI Generate API，等待返回即可
- **加密传输**: 图片通过 pixel_shuffle_2 加密传输，本地自动解密
- **元数据清理**: 自动去除工作流元数据，保护工作流隐私
- **灵活参数**: 支持自定义提示词、种子、采样步数、CFG、分辨率、模型、LoRA 等

## 前置要求

需要先在 [Modal](https://modal.com/) 上部署 ComfyUI 服务（含 Generate API 端点）。部署脚本见项目根目录的 `comfyapp.py`。

## 安装方法

### 方式一：克隆仓库

```bash
cd /path/to/nekro-agent/plugins/workdir
git clone <repo-url> modal_comfyui
```

### 方式二：手动下载

将 `modal_comfyui/` 目录复制到 `nekro-agent/plugins/workdir/` 下，重启 Nekro Agent 即可。

## 使用方法

直接向 AI 发起绘图请求：

```
画一个蓝色头发的女孩
```

AI 会自动调用 `draw_image` 工具生成图片并发送。

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| positive_prompt | str | 必填 | 正向提示词，使用英文 danbooru tag 效果最佳 |
| negative_prompt | str | 内置默认 | 负向提示词 |
| seed | int | 随机 | 随机种子，-1=随机 |
| steps | int | 32 | 采样步数，推荐 20-40 |
| cfg | float | 6.5 | CFG 引导系数，推荐 5-10 |
| width | int | 896 | 图片宽度 |
| height | int | 1152 | 图片高度 |
| sampler_name | str | euler_ancestral | 采样器名称 |
| scheduler | str | normal | 调度器 |
| denoise | float | 1.0 | 去噪强度 0-1 |
| checkpoint | str | 工作流默认 | 大模型文件名 |
| lora_name | str | 工作流默认 | LoRA 文件名 |
| lora_strength | float | 1.0 | LoRA 强度 0-2 |

## 配置说明

在 Nekro Agent 插件管理界面配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| GENERATE_API_URL | (需填写) | Modal ComfyUI Generate 端点 URL |
| DECRYPT_PASSWORD | shiratamakeki_nanoda | 解密密码，需与工作流 EncryptImage 节点一致 |
| DEFAULT_NEGATIVE_PROMPT | bad quality, worst quality... | 默认负向提示词 |
| REQUEST_TIMEOUT | 660 | HTTP 请求超时时间（秒） |
| OUTPUT_DIR | ./data/modal_comfyui_output | 图片本地保存路径 |

## 工作原理

```
用户请求 → AI 调用 draw_image
  → POST Generate API（含提示词等参数）
  → Modal 服务端：注入工作流 → ComfyUI 生成 → 去元数据 → 返回加密 PNG
  → 插件本地：解密图片 → 去除残余元数据 → 保存文件
  → AI 调用 send_image 发送给用户
```

## 目录结构

```
modal_comfyui/
├── __init__.py          # 插件入口
├── plugin.py            # 插件主逻辑（配置、API 调用、draw_image 工具）
├── decryption_utils.py  # pixel_shuffle 解密算法
├── metadata_utils.py    # PNG 元数据去除
└── README.md
```

## 许可证

MIT License

## 致谢

- [Nekro Agent](https://github.com/KroMiose/nekro-agent) - 插件框架
- [Modal](https://modal.com/) - 云端 GPU 平台
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - 图片生成后端
- [comfyui-encrypt-image](https://github.com/viyiviyi/comfyui-encrypt-image) - 图片加密节点
