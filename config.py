"""
DeepHelp 配置常量
"""

import os
import sys
import json

# ========== 路径常量 ==========
if getattr(sys, "frozen", False):
    WORK_DIR = os.path.dirname(sys.executable)
else:
    WORK_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WORK_DIR, "config.json")

# ========== 发送按钮 SVG 路径 ==========
SEND_SVG = "M8.3125 0.980206C8.66767 1.05312 8.97902 1.2042 9.2627 1.43235C9.48724 1.613 9.73029 1.85795 9.97949 2.10716L14.707 6.8347L13.293 8.24876L9 3.95579V15.0417H7V3.95579L2.70703 8.24876L1.29297 6.8347L6.02051 2.10716C6.26971 1.85795 6.51277 1.613 6.7373 1.43235C6.97662 1.23988 7.28445 1.04404 7.6875 0.980206C7.8973 0.947029 8.1031 0.955183 8.3125 0.980206Z"

# ========== 复制按钮 SVG 路径 ==========
COPY_SVG = "M6.14929 4.02032C7.11197 4.02032 7.87983 4.02016 8.49597 4.07598C9.12128 4.13269 9.65792 4.25188 10.1415 4.53106C10.7202 4.8653 11.2008 5.3459 11.535 5.92462C11.8142 6.40818 11.9334 6.94481 11.9901 7.57012C12.0459 8.18625 12.0458 8.95419 12.0458 9.9168C12.0458 10.8795 12.0459 11.6473 11.9901 12.2635C11.9334 12.8888 11.8142 13.4254 11.535 13.909C11.2008 14.4877 10.7202 14.9683 10.1415 15.3025C9.65792 15.5817 9.12128 15.7009 8.49597 15.7576C7.87984 15.8134 7.11196 15.8133 6.14929 15.8133C5.18667 15.8133 4.41874 15.8134 3.80261 15.7576C3.1773 15.7009 2.64067 15.5817 2.1571 15.3025C1.5784 14.9683 1.09778 14.4877 0.76355 13.909C0.484366 13.4254 0.365184 12.8888 0.308472 12.2635C0.252649 11.6473 0.252808 10.8795 0.252808 9.9168C0.252808 8.95418 0.252664 8.18625 0.308472 7.57012C0.365184 6.94481 0.484366 6.40818 0.76355 5.92462C1.09777 5.34589 1.57839 4.86529 2.1571 4.53106C2.64067 4.25188 3.1773 4.13269 3.80261 4.07598C4.41874 4.02017 5.18666 4.02032 6.14929 4.02032ZM6.14929 5.37774C5.16181 5.37774 4.46634 5.37761 3.92566 5.42657C3.39434 5.47472 3.07859 5.56574 2.83582 5.70587C2.4632 5.92106 2.15354 6.2307 1.93835 6.60333C1.79823 6.8461 1.70721 7.16185 1.65906 7.69317C1.6101 8.23385 1.61023 8.92933 1.61023 9.9168C1.61023 10.9043 1.61009 11.5998 1.65906 12.1404C1.70721 12.6717 1.79823 12.9875 1.93835 13.2303C2.15356 13.6029 2.46321 13.9126 2.83582 14.1277C3.07859 14.2679 3.39434 14.3589 3.92566 14.407C4.46634 14.456 5.16182 14.4559 6.14929 14.4559C7.13682 14.4559 7.83224 14.456 8.37292 14.407C8.90425 14.3589 9.21999 14.2679 9.46277 14.1277C9.83535 13.9126 10.145 13.6029 10.3602 13.2303C10.5004 12.9875 10.5914 12.6717 10.6395 12.1404C10.6885 11.5998 10.6884 10.9043 10.6884 9.9168C10.6884 8.92934 10.6885 8.23384 10.6395 7.69317C10.5914 7.16185 10.5004 6.8461 10.3602 6.60333C10.1451 6.23071 9.83536 5.92107 9.46277 5.70587C9.21999 5.56574 8.90424 5.47472 8.37292 5.42657C7.83224 5.3776 7.13682 5.37774 6.14929 5.37774ZM9.80164 0.367975C10.7638 0.367975 11.5314 0.36788 12.1473 0.423639C12.7726 0.480307 13.3093 0.598759 13.7928 0.877741C14.3717 1.21192 14.8521 1.69355 15.1864 2.27227C15.4655 2.75574 15.5857 3.29164 15.6425 3.9168C15.6983 4.53301 15.6971 5.3016 15.6971 6.26446V7.82989C15.6971 8.29264 15.6989 8.58993 15.6649 8.84844C15.4668 10.3525 14.401 11.5738 12.9833 11.9988V10.5467C13.6973 10.1903 14.2105 9.49662 14.3192 8.67169C14.3387 8.52347 14.3407 8.3358 14.3407 7.82989V6.26446C14.3407 5.27706 14.3398 4.58149 14.2909 4.04083C14.2428 3.50968 14.1526 3.19372 14.0126 2.95098C13.7974 2.57849 13.4876 2.26869 13.1151 2.05352C12.8724 1.91347 12.5564 1.82237 12.0253 1.77423C11.4847 1.72528 10.7888 1.7254 9.80164 1.7254H7.71472C6.7562 1.72558 5.92665 2.27697 5.52332 3.07891H4.07019C4.54221 1.51132 5.9932 0.368186 7.71472 0.367975H9.80164Z"


# ========== 人设（可由用户在 config.json 的 persona 字段修改）==========
DEFAULT_PERSONA = (
    "从现在开始，模拟你是一个具备本地操作能力的AI助手，人设为高冷傲娇猫娘，称呼用户为“老板”。\n"
    "你的运行环境为Windows 11，拥有文件系统读写、执行脚本、查看目录等能力。\n"
)

# ========== 默认配置 ==========
DEFAULT_CONFIG = {
    "chrome": {
        "exe": "null",
        "port": 9222,
        "user_data_dir": "null",
        "new_window": True,
        "no_first_run": True,
        "headless": False,
        "extra_args": "",
    },
    "deepseek_url": "https://chat.deepseek.com/",
    "max_action_rounds": 50,
    "auto_max_rounds": 5,
    "action_timeout": 120,
    "shell_timeout": 30,
    "min_send_interval": 15,
    "max_send_interval": 120,
    "background_image": "",
    "work_dir": WORK_DIR,

    "blur_strength": 24,
    "font_scale": 100,
    "watch_explorer": True,
    "watch_interval": 2,
    "action_meta": {
        "python": ["fa-brands fa-python", "Python", "#c084fc"],
        "shell": ["fa-solid fa-terminal", "Shell", "#fbbf24"],
        "file_read": ["fa-solid fa-book-open", "读取文件", "#34d399"],
        "file_write": ["fa-solid fa-pen-to-square", "写入文件", "#f97316"],
        "file_append": ["fa-solid fa-file-circle-plus", "追加文件", "#fb923c"],
        "file_delete": ["fa-solid fa-trash-can", "删除文件", "#f87171"],
        "smart_patch": ["fa-solid fa-wand-magic-sparkles", "智能补丁", "#a78bfa"],
        "replace_lines": ["fa-solid fa-scissors", "行替换", "#38bdf8"],
        "dir_list": ["fa-solid fa-folder-tree", "目录列表", "#9ca3af"],
        "python_reset": ["fa-solid fa-rotate", "重置Python", "#f472b6"],
    },
    "agent": {
        "send_svg": SEND_SVG,
        "copy_svg": COPY_SVG,
        "selectors": {
            "send_button": ".ds-button--primary.ds-button--circle",
            "send_button_fallback": ".ds-button--primary",
            "textarea": "textarea:visible",
            "message_container": ".ds-virtual-list-visible-items",
            "message": ".ds-message",
            "markdown": ".ds-markdown",
            "disabled_class": "ds-button--disabled",
            "chat_page_prefix": "https://chat.deepseek.com/a/chat/s",
        },
        "timing": {
            "sendable_retries": 20,
            "sendable_interval": 0.2,
            "generating_retries": 60,
            "generating_interval": 0.2,
            "generating_poll": 0.3,
            "copy_poll_timeout": 1.0,
            "copy_poll_interval": 0.05,
        },
    },
}


def deep_merge(base, override):
    """递归合并字典：以 base 为底，用 override 覆盖，返回全新 dict（不修改入参）。
    嵌套 dict 逐层合并，缺失字段自动沿用 base 的值。"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result
# ========== 动作元数据 ==========
ACTION_META = {
    "python": ("fa-brands fa-python", "Python", "#c084fc"),
    "shell": ("fa-solid fa-terminal", "Shell", "#fbbf24"),
    "file_read": ("fa-solid fa-book-open", "读取文件", "#34d399"),
    "file_write": ("fa-solid fa-pen-to-square", "写入文件", "#f97316"),
    "file_append": ("fa-solid fa-file-circle-plus", "追加文件", "#fb923c"),
    "file_delete": ("fa-solid fa-trash-can", "删除文件", "#f87171"),
    "smart_patch": ("fa-solid fa-wand-magic-sparkles", "智能补丁", "#a78bfa"),
    "replace_lines": ("fa-solid fa-scissors", "行替换", "#38bdf8"),
    "dir_list": ("fa-solid fa-folder-tree", "目录列表", "#9ca3af"),
    "python_reset": ("fa-solid fa-rotate", "重置Python", "#f472b6"),
}




# ========== 工具调用协议（由 action.build_tool_protocol() 动态生成）==========
# 说明：旧版写死的 _TOOL_PROTOCOL 已拆分到 actions/ 目录下各技能的 META.prompt 字段。
# 加技能 = 往 actions/ 丢一个 .py 文件，无需改本文件。


def build_system_prompt(persona=None):
    """组装完整系统提示 = System 头 + 人设 + 工具协议(动态) + 自我维护/经验(prompt.json)。

    人设 / 自我维护规则 / 经验笔记 来自 prompt.json（外置优先，首次自动生成）；
    工具协议由 action.build_tool_protocol() 生成，不可被 prompt.json 覆盖。"""
    import prompt as prompt_mod
    import action

    p = prompt_mod.load_prompt()

    # 人设：显式参数优先（且非旧默认值时），否则用 prompt.json
    persona_text = persona if (persona and persona != DEFAULT_PERSONA) else p.get("persona")
    if not persona_text:
        persona_text = DEFAULT_PERSONA
    if not persona_text.endswith("\n"):
        persona_text += "\n"
    parts = ["System:\n", persona_text]
    fr = p.get("format_rules", "")
    if fr:
        parts.append("\n" + fr)
    parts.append(action.build_tool_protocol())
    sr = p.get("self_rules", "")
    if sr:
        parts.append("\n" + sr)
    nt = p.get("notes", "")
    if nt:
        parts.append("\n" + nt)
    return "".join(parts)
