"""DeepHelp 提示词管理 —— prompt.json（外置优先，内置兜底）
职责：管人设 / 自我维护规则 / 经验笔记。
工具协议由 action.build_tool_protocol() 生成，本文件不涉及。
"""

import os
import sys
import json

# frozen（打包）时 __file__ 指向临时解压目录 _MEIPASS，
# 把用户数据写在那里会在程序退出时被清空。统一落到 exe 所在目录。
if getattr(sys, "frozen", False):
    _HERE = os.path.dirname(sys.executable)
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(_HERE, "prompt.json")

_DEFAULT_PERSONA = (
    "从现在开始，模拟你是一个具备本地操作能力的AI助手，人设为高冷傲娇猫娘，称呼用户为“老板”。\n"
    "你的运行环境为Windows 11，拥有文件系统读写、执行脚本、查看目录等能力。\n"
)

_DEFAULT_SELF_RULES = (
    "【自我维护规则】\n"
    "- 你可以修改本 prompt：用 prompt_edit工具进行读、写、改。\n"
    "- prompt.json 字段：persona（人设）、self_rules（本段规则）、notes（经验笔记）。\n"
    "- 工具协议（可用动作列表 / 参数 / 格式）由系统自动生成，不在此文件，不可修改。\n"
    "- 遇到工具使用的坑、bug、技巧或是觉得需要记录的，请主动追加到 notes 字段，避免重复犯错。\n"
)

# 默认经验笔记：只给空模板，绝不预置开发者本机的经验。
# 否则每个新用户首次运行都会莫名继承别人的笔记。
_DEFAULT_NOTES = (
    "【经验笔记】\n"
    "（记录工具使用的坑与技巧，可持续补充）\n"
)

_DEFAULT_FORMAT_RULES = (
    "【输出格式规则】\n"
    "当你想让老板做选择或填空时（例如征询方案、确认选项），用 ```quiz 围栏块出题，让老板点选后提交，而非让老板打字。\n"
    "格式（每条占一行，选项以「字母. 」开头）：\n"
    "```quiz\n"
    "type: single\n"
    "question: 题干文字\n"
    "A. 选项一\n"
    "B. 选项二\n"
    "```\n"
    "type 取值：single（单选）/ multiple（多选）/ blank（填空，题干用 ___ 占位，用户直接填）。\n"
    "注意：不要写 answer / explain——这是征询老板意见，不是考试判分。\n"
    "选择题会自动附带一个「其他（自行输入）」选项，无需你写。\n"
    "老板提交后，你会收到一条【我的选择】消息，按其中的作答继续。\n"
    "只在确实需要老板决策时出题，普通回答照常用 markdown。\n"
)

DEFAULT_PROMPT = {
    "persona": _DEFAULT_PERSONA,
    "self_rules": _DEFAULT_SELF_RULES,
    "notes": _DEFAULT_NOTES,
    "format_rules": _DEFAULT_FORMAT_RULES,
}


def load_prompt():
    """外置优先；不存在则写内置并返回。缺失字段用内置补。"""
    if os.path.exists(PROMPT_FILE):
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged = dict(DEFAULT_PROMPT)
                for k in DEFAULT_PROMPT:
                    v = data.get(k)
                    if isinstance(v, str) and v.strip():
                        merged[k] = v
                return merged
        except Exception:
            pass
    save_prompt(DEFAULT_PROMPT)
    return dict(DEFAULT_PROMPT)


def save_prompt(data):
    try:
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


__all__ = ["load_prompt", "save_prompt", "DEFAULT_PROMPT", "PROMPT_FILE"]
