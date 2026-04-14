"""
Modal ComfyUI 绘图插件

通过 Modal 云端 ComfyUI 的 Generate API 生成动漫风格图片。
一次 POST 请求完成生成，图片经加密传输后本地解密。

## 主要功能

- **云端绘图**: 调用 Modal ComfyUI Generate API，一次请求拿到结果
- **加密传输**: 图片通过 pixel_shuffle_2 加密传输，本地自动解密
- **元数据清理**: 自动去除工作流元数据，保护工作流隐私

## 使用方法

AI 调用 draw_image 工具，传入提示词等参数即可生成图片。
"""

import asyncio
import time
import uuid
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from pydantic import Field

from nekro_agent.api import core, schemas
from nekro_agent.api.plugin import ConfigBase, NekroPlugin, SandboxMethodType

from .decryption_utils import decrypt_process
from .metadata_utils import remove_workflow_metadata

# ============================================================
# 插件实例
# ============================================================

plugin = NekroPlugin(
    name="Modal ComfyUI 绘图",
    module_name="nekro_plugin_modal_comfyui",
    description="通过 Modal 云端 ComfyUI Generate API 生成动漫风格图片，支持自定义提示词和参数。",
    version="2.1.0",
    author="ShiratamaKeki",
    url="",
    support_adapter=["onebot_v11", "discord", "telegram"],
)


# ============================================================
# 配置定义
# ============================================================


@plugin.mount_config()
class ModalComfyUIConfig(ConfigBase):
    """Modal ComfyUI 绘图配置"""

    GENERATE_API_URL: str = Field(
        default="https://your-workspace--example-comfyapp-comfyui-generate.modal.run",
        title="Generate API 地址",
        description="Modal ComfyUI generate 端点 URL",
    )

    DECRYPT_PASSWORD: str = Field(
        default="123qwe",
        title="加密/解密密码",
        description="与 ComfyUI 工作流中 EncryptImage 节点设置的密码一致",
    )

    DEFAULT_NEGATIVE_PROMPT: str = Field(
        default=(
            "bad quality, worst quality, worst detail, "
            "(bad hands:1.2), missing fingers, "
            "(extra fingers, fused fingers:1.1), text, username"
        ),
        title="默认负向提示词",
        description="当用户未指定负向提示词时使用的默认值",
    )

    REQUEST_TIMEOUT: int = Field(
        default=660,
        title="请求超时时间(秒)",
        description="调用 Generate API 的 HTTP 超时时间，需大于服务端最大生成时间",
    )

    OUTPUT_DIR: str = Field(
        default="./data/modal_comfyui_output",
        title="图片输出目录",
        description="生成的图片本地保存路径",
    )

    # --- 生成参数默认值（匹配当前工作流模板，换工作流时在此修改） ---

    DEFAULT_STEPS: int = Field(
        default=32,
        title="默认采样步数",
        description="KSampler 的默认 steps，推荐 20-40",
    )

    DEFAULT_CFG: float = Field(
        default=6.5,
        title="默认 CFG 引导系数",
        description="KSampler 的默认 cfg，推荐 5-10",
    )

    DEFAULT_WIDTH: int = Field(
        default=896,
        title="默认图片宽度",
        description="EmptyLatentImage 的默认宽度",
    )

    DEFAULT_HEIGHT: int = Field(
        default=1152,
        title="默认图片高度",
        description="EmptyLatentImage 的默认高度",
    )

    DEFAULT_SAMPLER_NAME: str = Field(
        default="euler_ancestral",
        title="默认采样器",
        description="KSampler 的默认 sampler_name，可选 euler, dpmpp_2m, dpmpp_sde 等",
    )

    DEFAULT_SCHEDULER: str = Field(
        default="normal",
        title="默认调度器",
        description="KSampler 的默认 scheduler，可选 karras, exponential, sgm_uniform",
    )

    DEFAULT_DENOISE: float = Field(
        default=1.0,
        title="默认去噪强度",
        description="KSampler 的默认 denoise，1.0=完全生成，img2img 建议 0.3-0.7",
    )

    DEFAULT_CHECKPOINT: str = Field(
        default="",
        title="默认大模型",
        description="CheckpointLoaderSimple 的默认 ckpt_name，留空则使用工作流内置值",
    )

    DEFAULT_LORA_NAME: str = Field(
        default="",
        title="默认 LoRA",
        description="LoraLoader 的默认 lora_name，留空则使用工作流内置值",
    )

    DEFAULT_LORA_STRENGTH: float = Field(
        default=1.0,
        title="默认 LoRA 强度",
        description="LoraLoader 的默认 strength，范围 0-2",
    )

    # --- 可用模型列表（用于 AI 提示注入，让 AI 知道能选什么模型） ---

    AVAILABLE_CHECKPOINTS: str = Field(
        default=(
            "waiIllustriousSDXL_v160.safetensors, "
            "zukiCuteILL_v60.safetensors, "
            "illustmixluminous_v21.safetensors, "
            "oeailIllustriousXLMore_oeaiV12.safetensors, "
            "realvisxlV50_v30InpaintBakedvae.safetensors"
        ),
        title="可用大模型列表",
        description="逗号分隔的 checkpoint 文件名列表，会注入到 AI 提示中",
    )

    AVAILABLE_LORAS: str = Field(
        default=(
            "IL_花園Senera3_v1.safetensors, "
            "neri02.safetensors, "
            "Ayatsuki_Nora0.3_lokr-000060.safetensors, "
            "kawaii_CUTE2712_Illustrious_v1.0.safetensors, "
            "baiyuA-000150-Fourth Furnace.safetensors, "
            "baiyuA-000140.safetensors, "
            "Shuvi-UC-v1.safetensors, "
            "IzunaLora.safetensors, "
            "Nachoneko_IL.safetensors, "
            "shiratma_vtuber.safetensors, "
            "铃兰2linglan-SDXL-lora-2024.10.19-version1-000024.safetensors, "
            "鬼针草-000070.safetensors, "
            "baku-p_pony_v1.safetensors, "
            "weijiang_v2.safetensors, "
            "Misono_Ichika.safetensors, "
            "ill-xl-01-tyomimas_1-000032.safetensors, "
            "PVC_Style_Movable_Figure_Model_XL.safetensors, "
            "水梓azusa-swim_blue_archive_PONY_last.safetensors, "
            "guizhencao3——【noob】hans.safetensors, "
            "z-image-turbo-yachiyo.safetensors, "
            "森亚露露卡Moria Luluka&Cure Arcana Shadow_v2_ill.safetensors, "
            "futaba_sharo_20260129-000034.safetensors"
        ),
        title="可用 LoRA 列表",
        description="逗号分隔的 LoRA 文件名列表，会注入到 AI 提示中",
    )


config: ModalComfyUIConfig = plugin.get_config(ModalComfyUIConfig)


# ============================================================
# 工具函数
# ============================================================


def _decrypt_and_clean(encrypted_bytes: bytes, password: str) -> bytes:
    """解密图片并去除工作流元数据"""
    encrypted_image = Image.open(BytesIO(encrypted_bytes))
    decrypted_image = decrypt_process(encrypted_image, password)
    clean_bytes = remove_workflow_metadata(decrypted_image)
    return clean_bytes


def _format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


async def _call_generate_api(
    positive_prompt: str,
    negative_prompt: str,
    seed=None, steps=None, cfg=None,
    width=None, height=None,
    sampler_name=None, scheduler=None, denoise=None,
    checkpoint=None, lora_name=None, lora_strength=None,
) -> bytes:
    """调用 Modal ComfyUI 的 /generate API"""
    payload = {
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
    }

    # 只传非 None 的可选参数
    optional = {
        "seed": seed, "steps": steps, "cfg": cfg,
        "width": width, "height": height,
        "sampler_name": sampler_name, "scheduler": scheduler,
        "denoise": denoise, "checkpoint": checkpoint,
        "lora_name": lora_name, "lora_strength": lora_strength,
    }
    for k, v in optional.items():
        if v is not None:
            payload[k] = v

    api_url = config.GENERATE_API_URL.rstrip("/")
    core.logger.info(f"[Modal ComfyUI] 调用 Generate API: {api_url}")

    def _do_request() -> bytes:
        resp = requests.post(api_url, json=payload, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code != 200:
            try:
                error_detail = resp.json().get("error", resp.text[:200])
            except Exception:
                error_detail = resp.text[:200]
            raise RuntimeError(f"Generate API 错误 [{resp.status_code}]: {error_detail}")

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            raise RuntimeError(f"Generate API 返回非图片: {content_type}")

        return resp.content

    content = await asyncio.to_thread(_do_request)
    core.logger.info(f"[Modal ComfyUI] Generate API 响应成功, 大小: {len(content)} bytes")
    return content


# ============================================================
# Sandbox 方法（AI 可调用的工具）
# ============================================================


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="draw_image",
    description=(
        "使用 Modal 云端 ComfyUI 生成动漫风格图片。\n"
        "参数:\n"
        "  positive_prompt (str): 正向提示词，使用英文 danbooru tag 效果最佳\n"
        "  negative_prompt (str, 可选): 负向提示词，为空则使用默认值\n"
        "  seed (int, 可选): 随机种子，-1=随机\n"
        "  steps (int, 可选): 采样步数，默认32，推荐20-40\n"
        "  cfg (float, 可选): CFG引导系数，默认6.5，推荐5-10\n"
        "  width (int, 可选): 图片宽度，默认896\n"
        "  height (int, 可选): 图片高度，默认1152\n"
        "  sampler_name (str, 可选): 采样器，默认'euler_ancestral'\n"
        "  scheduler (str, 可选): 调度器，默认'normal'\n"
        "  denoise (float, 可选): 去噪强度0-1，默认1.0\n"
        "  checkpoint (str, 可选): 大模型文件名\n"
        "  lora_name (str, 可选): LoRA文件名\n"
        "  lora_strength (float, 可选): LoRA强度0-2，默认1.0\n"
        "返回: 生成图片的文件路径，请使用 send_image 将图片发送给用户"
    ),
)
async def draw_image(
    _ctx: schemas.AgentCtx,
    positive_prompt: str,
    negative_prompt: str = "",
    seed: int = -1,
    steps: int = -1,
    cfg: float = -1,
    width: int = -1,
    height: int = -1,
    sampler_name: str = "",
    scheduler: str = "",
    denoise: float = -1,
    checkpoint: str = "",
    lora_name: str = "",
    lora_strength: float = -1,
) -> str:
    """Draw Image using Modal ComfyUI Generate API

    Generate anime-style images via cloud ComfyUI service.

    Args:
        _ctx: Agent context
        positive_prompt: Positive prompt using danbooru tags
        negative_prompt: Negative prompt (empty = use default)
        seed: Random seed (-1 = random)
        steps: Sampling steps (-1 = default 32)
        cfg: CFG guidance scale (-1 = default 6.5)
        width: Image width (-1 = default 896)
        height: Image height (-1 = default 1152)
        sampler_name: Sampler name (empty = default euler_ancestral)
        scheduler: Scheduler (empty = default normal)
        denoise: Denoise strength (-1 = default 1.0)
        checkpoint: Checkpoint filename (empty = default)
        lora_name: LoRA filename (empty = default)
        lora_strength: LoRA strength (-1 = default 1.0)

    Returns:
        str: Path to generated image file

    Example:
        draw_image(_ck, "1girl, solo, blue hair, smile")
    """
    try:
        if not negative_prompt:
            negative_prompt = config.DEFAULT_NEGATIVE_PROMPT

        # AI 未指定的参数（-1 或空）使用配置中的默认值
        actual_seed = seed if seed >= 0 else None
        actual_steps = steps if steps > 0 else config.DEFAULT_STEPS
        actual_cfg = cfg if cfg > 0 else config.DEFAULT_CFG
        actual_width = width if width > 0 else config.DEFAULT_WIDTH
        actual_height = height if height > 0 else config.DEFAULT_HEIGHT
        actual_sampler = sampler_name if sampler_name else config.DEFAULT_SAMPLER_NAME
        actual_scheduler = scheduler if scheduler else config.DEFAULT_SCHEDULER
        actual_denoise = denoise if denoise >= 0 else config.DEFAULT_DENOISE
        actual_checkpoint = checkpoint if checkpoint else (config.DEFAULT_CHECKPOINT or None)
        actual_lora = lora_name if lora_name else (config.DEFAULT_LORA_NAME or None)
        actual_lora_str = lora_strength if lora_strength >= 0 else config.DEFAULT_LORA_STRENGTH

        unique_id = str(uuid.uuid4())[:8]

        core.logger.info("[Modal ComfyUI] 开始生成图片...")
        start_time = time.time()

        # 调用 Generate API
        encrypted_bytes = await _call_generate_api(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            seed=actual_seed,
            steps=actual_steps,
            cfg=actual_cfg,
            width=actual_width,
            height=actual_height,
            sampler_name=actual_sampler,
            scheduler=actual_scheduler,
            denoise=actual_denoise,
            checkpoint=actual_checkpoint,
            lora_name=actual_lora,
            lora_strength=actual_lora_str,
        )

        # 解密并保存
        clean_bytes = await asyncio.to_thread(
            _decrypt_and_clean, encrypted_bytes, config.DECRYPT_PASSWORD
        )

        # NekroAgent 的 send_msg_file 只接受 "shared" 或 "uploads" 路径
        # 必须保存到 /app/shared/ 下才能被 AI 正常发送
        output_dir = Path("/app/shared/comfyui_output")
        output_dir.mkdir(parents=True, exist_ok=True)

        if actual_seed is not None:
            filename = f"comfyui_{actual_seed}_{unique_id}.png"
        else:
            filename = f"comfyui_{unique_id}.png"

        output_path = output_dir / filename
        with open(output_path, "wb") as f:
            f.write(clean_bytes)

        elapsed = time.time() - start_time
        file_size = _format_size(len(clean_bytes))

        core.logger.info(
            f"[Modal ComfyUI] 图片生成完成: {output_path} ({file_size}, {elapsed:.1f}s)"
        )

        return str(output_path)

    except requests.exceptions.ConnectionError:
        core.logger.error("[Modal ComfyUI] 无法连接到 ComfyUI 服务器")
        return "错误: 无法连接到 Modal ComfyUI 服务器，请检查服务是否已部署且正在运行"
    except requests.exceptions.Timeout:
        core.logger.error("[Modal ComfyUI] 请求超时")
        return "错误: 请求超时，ComfyUI 可能正在冷启动或队列繁忙"
    except RuntimeError as e:
        core.logger.error(f"[Modal ComfyUI] {e}")
        return f"错误: {e}"
    except Exception as e:
        core.logger.error(f"[Modal ComfyUI] 生成失败: {e}", exc_info=True)
        return f"错误: 图片生成失败 - {e}"


# ============================================================
# 提示注入
# ============================================================


@plugin.mount_prompt_inject_method(name="modal_comfyui_prompt_inject")
async def modal_comfyui_prompt_inject(_ctx: schemas.AgentCtx) -> str:
    """绘图功能提示注入"""
    return f"""Modal ComfyUI Drawing Plugin Available:
Call draw_image(positive_prompt, ...) to generate anime-style images, then use send_image to send the result.

Default parameters (used when not specified):
- steps: {config.DEFAULT_STEPS}, cfg: {config.DEFAULT_CFG}, sampler: {config.DEFAULT_SAMPLER_NAME}, scheduler: {config.DEFAULT_SCHEDULER}
- resolution: {config.DEFAULT_WIDTH}x{config.DEFAULT_HEIGHT}, denoise: {config.DEFAULT_DENOISE}
- Use English danbooru tags for positive_prompt, e.g. "1girl, solo, blue hair, smile"

Available checkpoints:
{config.AVAILABLE_CHECKPOINTS}

Available LoRAs:
{config.AVAILABLE_LORAS}

Tips:
- Only specify parameters you want to change, others will use defaults above
- seed=-1 means random, specify a seed to reproduce the same image
- checkpoint and lora_name must use exact filenames from the lists above"""


# ============================================================
# 插件生命周期
# ============================================================


@plugin.mount_init_method()
async def initialize_plugin():
    """插件初始化"""
    core.logger.info("[Modal ComfyUI] 插件初始化...")
    core.logger.info(f"[Modal ComfyUI] API 地址: {config.GENERATE_API_URL}")
    core.logger.info(f"[Modal ComfyUI] 输出目录: {config.OUTPUT_DIR}")

    output_dir = Path(config.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    core.logger.success("[Modal ComfyUI] 插件初始化完成")


@plugin.mount_cleanup_method()
async def cleanup_plugin():
    """清理插件资源"""
    core.logger.info("[Modal ComfyUI] 插件资源清理完成")
