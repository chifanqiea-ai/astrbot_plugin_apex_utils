"""Apex Legends 战绩查询插件的常量与中英映射表。

本模块不依赖 AstrBot 框架，可独立测试。
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------------------

#: Mozambique Heirloom API，同时可通过 api.apexlegendsstatus.com 访问（同一套接口）。
DEFAULT_API_BASE = "https://api.mozambiquehe.re"

#: 插件展示用的数据来源标识（API 使用条款要求注明数据来源）。
DATA_SOURCE_LABEL = "数据来源：Mozambique Heirloom API (apexlegendsstatus.com)"

#: 平台参数 -> 展示名。PC 平台请填写 EA / Origin 账号名（Steam 玩家同样使用绑定的 EA 账号名）。
PLATFORMS: dict[str, str] = {
    "PC": "PC (EA/Origin)",
    "PS4": "PlayStation",
    "X1": "Xbox",
    "SWITCH": "Nintendo Switch",
}

#: 指令中可接受的平台写法 -> API 平台值
PLATFORM_ALIASES: dict[str, str] = {
    "pc": "PC",
    "origin": "PC",
    "ea": "PC",
    "steam": "PC",
    "ps": "PS4",
    "ps4": "PS4",
    "ps5": "PS4",
    "playstation": "PS4",
    "xbox": "X1",
    "x1": "X1",
    "xb": "X1",
    "switch": "SWITCH",
    "ns": "SWITCH",
    "ns2": "SWITCH",
    "switch2": "SWITCH",
}

DEFAULT_PLATFORM = "PC"

# ---------------------------------------------------------------------------
# 段位
# ---------------------------------------------------------------------------

#: Apex 段位英文名 -> 中文名
RANK_NAMES: dict[str, str] = {
    "Rookie": "菜鸟",
    "Bronze": "青铜",
    "Silver": "白银",
    "Gold": "黄金",
    "Platinum": "铂金",
    "Diamond": "钻石",
    "Master": "大师",
    "Masters": "大师",
    "Predator": "顶尖猎杀者",
    "Apex Predator": "顶尖猎杀者",
    "Unranked": "未定级",
    "None": "未定级",
}

#: 段位英文名 -> 段位图标文件名（Mozambique Heirloom API 的 rankImg 资源）
RANK_ICON_NAMES: dict[str, str] = {
    "Rookie": "rookie",
    "Bronze": "bronze",
    "Silver": "silver",
    "Gold": "gold",
    "Platinum": "platinum",
    "Diamond": "diamond",
    "Master": "master",
    "Masters": "master",
    "Predator": "predator",
    "Apex Predator": "predator",
}

#: 罗马数字分段（Apex 段位每一大段内的 I~IV，I 为最高）
DIVISION_ROMAN: dict[int, str] = {1: "I", 2: "II", 3: "III", 4: "IV"}

#: 排位分（RP）段位门槛，用于在没有 rankDiv 时推算小段位。
#: 数值随赛季调整，仅作为兜底展示，不影响主流程。
RP_DIV_THRESHOLDS: dict[str, int] = {
    "Rookie": 0,
    "Bronze": 1000,
    "Silver": 2000,
    "Gold": 3000,
    "Platinum": 4000,
    "Diamond": 5000,
    "Master": 10000,
}

# ---------------------------------------------------------------------------
# 传奇（英雄）
# ---------------------------------------------------------------------------

LEGEND_NAMES: dict[str, str] = {
    "Alter": "奥尔特",
    "Ash": "艾许",
    "Ballistic": "弹道",
    "Bangalore": "班加罗尔",
    "Bloodhound": "寻血猎犬",
    "Catalyst": "催化剂",
    "Caustic": "侵蚀",
    "Conduit": "导管",
    "Crypto": "密客",
    "Fuse": "暴雷",
    "Gibraltar": "直布罗陀",
    "Horizon": "地平线",
    "Lifeline": "生命线",
    "Loba": "罗芭",
    "Mad Maggie": "疯狂玛吉",
    "Maggie": "疯狂玛吉",
    "Mirage": "幻象",
    "Newcastle": "纽卡斯尔",
    "Octane": "辛烷",
    "Pathfinder": "探路者",
    "Rampart": "兰伯特",
    "Revenant": "亡灵",
    "Seer": "希尔",
    "Sparrow": "斯派洛",
    "Valkyrie": "瓦尔基里",
    "Vantage": "万蒂奇",
    "Wattson": "沃特森",
    "Wraith": "恶灵",
    # 以下为改名 / 变体写法
    "Mad Maggie (Warlord)": "疯狂玛吉",
    "Skirmisher": "突击位",
}

# ---------------------------------------------------------------------------
# 数据卡（tracker）名称映射
# ---------------------------------------------------------------------------

TRACKER_NAMES: dict[str, str] = {
    "kills": "击杀",
    "damage": "伤害",
    "wins": "胜场",
    "matches": "场次",
    "games_played": "场次",
    "games": "场次",
    "headshots": "爆头",
    "care_package_kills": "空投武器击杀",
    "season_kills": "赛季击杀",
    "season_wins": "赛季胜场",
    "season_damage": "赛季伤害",
    "br_kills": "大逃杀击杀",
    "arenas_kills": "竞技场击杀",
    "ranked_kills": "排位击杀",
    "ranked_wins": "排位胜场",
    "ranked_damage": "排位伤害",
    "level": "等级",
    "total_kills": "总击杀",
    "total_damage": "总伤害",
    "total_wins": "总胜场",
    "total_games": "总局数",
    "total_headshots": "总爆头",
    "total_shots": "总命中",
    "total_shots_hit": "总命中",
    "kills_as_kill_leader": "击杀领先者击杀",
    "damage_as_kill_leader": "击杀领先者伤害",
    "wins_as_kill_leader": "击杀领先者胜场",
    "games_as_kill_leader": "击杀领先者场次",
    "kd": "KD",
    "kd_ratio": "KD",
    "kdr": "KD",
    "win_rate": "胜率",
    "revives": "救援次数",
    "respawns": "复活次数",
    "executions": "处决",
    "finishers": "处决",
    "assists": "助攻",
    "top3": "前三名",
    "top_3": "前三名",
    "top5": "前五名",
    "top_5": "前五名",
    "weapon_ar_kills": "突击步枪击杀",
    "weapon_smg_kills": "冲锋枪击杀",
    "weapon_lmg_kills": "轻机枪击杀",
    "weapon_sniper_kills": "狙击枪击杀",
    "weapon_shotgun_kills": "霰弹枪击杀",
    "weapon_pistol_kills": "手枪击杀",
    "weapon_marksman_kills": "精确射手击杀",
    "care_package_weapon_kills": "空投武器击杀",
    "ranked_score": "排位分",
    "rank_score": "排位分",
    "br_score": "大逃杀排位分",
    "arena_score": "竞技场分数",
    "damage_per_match": "场均伤害",
    "kills_per_match": "场均击杀",
    "season_ranked_kills": "赛季排位击杀",
    "shields_charged": "护盾充能",
    "ordnance_destroyed": "摧毁投掷物",
    "silenced_enemies": "沉默敌人",
    "scans": "扫描次数",
}

#: 总览里优先展示的数据卡（按顺序），未命中的会按原始顺序补齐。
PREFERRED_TRACKERS: tuple[str, ...] = (
    "kills",
    "damage",
    "wins",
    "matches",
    "headshots",
    "care_package_kills",
    "kd_ratio",
    "kdr",
    "revives",
    "respawns",
    "season_kills",
    "ranked_kills",
)

#: 总览表格最多展示多少条数据卡。
MAX_TRACKER_ROWS = 8

#: 不需要展示的数据卡（重复 / 无意义 / 内部字段），比较时会统一转小写。
IGNORED_TRACKERS: frozenset[str] = frozenset(
    {
        "level",
        "xp",
        "name",
        "key",
        "value",
        "updated",
        "imgassets",  # v5 里混在传奇数据中的图标元数据
        "specialEvent_kills".lower(),
        "specialEvent_damage".lower(),
        "specialEvent_wins".lower(),
        "specialEvent_matches".lower(),
        "br_kills",
    }
)

# ---------------------------------------------------------------------------
# 错误文案
# ---------------------------------------------------------------------------

ERROR_MESSAGES: dict[str, str] = {
    "NO_API_KEY": (
        "❌ 还没有配置 API Key，无法查询战绩。\n"
        "请在 AstrBot 管理面板 → 插件管理 → Apex 战绩查询 → 配置 中填写 `api_key`。\n"
        "免费申请地址：https://apexlegendsapi.com/auth （注册后即可获得 Key）"
    ),
    "INVALID_API_KEY": "❌ API Key 无效或已被删除，请到 https://apexlegendsapi.com/auth 重新申请后更新配置。",
    "NOT_FOUND": "❌ 没有找到该玩家，请检查 EA ID 是否填写正确（PC 平台请填 EA/Origin 账号名，不是 Steam 昵称）。",
    "RATE_LIMITED": "⏳ 触发 API 限流（免费额度约 2 次/秒），请等几秒再试。",
    "UNKNOWN_PLATFORM": "❌ 未知平台，可用平台：pc / ps / xbox / switch 。",
    "API_ERROR": "❌ API 返回错误：{message}",
    "TIMEOUT": "❌ 请求 Apex 数据源超时，请稍后重试。",
    "NETWORK": "❌ 连接 Apex 数据源失败：{message}",
    "EMPTY_RESULT": "❌ 数据源没有返回该玩家的战绩数据（该玩家可能从未玩过 Apex）。",
}

__all__ = [
    "DATA_SOURCE_LABEL",
    "DEFAULT_API_BASE",
    "DEFAULT_PLATFORM",
    "DIVISION_ROMAN",
    "ERROR_MESSAGES",
    "IGNORED_TRACKERS",
    "LEGEND_NAMES",
    "MAX_TRACKER_ROWS",
    "PLATFORMS",
    "PLATFORM_ALIASES",
    "PREFERRED_TRACKERS",
    "RANK_ICON_NAMES",
    "RANK_NAMES",
    "RP_DIV_THRESHOLDS",
    "TRACKER_NAMES",
]


def translate_rank(rank_name: Any) -> str:
    """把 API 返回的段位英文名翻译成中文，未知时原样返回。"""
    if not rank_name:
        return "未定级"
    text = str(rank_name).strip()
    return RANK_NAMES.get(text, text)


def translate_legend(legend_name: Any) -> str:
    """把 API 返回的传奇英文名翻译成中文，未知时原样返回。"""
    if not legend_name:
        return "未知"
    text = str(legend_name).strip()
    return LEGEND_NAMES.get(text, text)


#: 动态赛季数据卡，如 ``wins_season_2`` -> 胜场（第2赛季）
_SEASON_TRACKER_RE = re.compile(r"^(?P<base>.+)_season_(?P<season>\d+)$")


def translate_tracker(tracker_key: Any) -> str:
    """把 API 返回的 tracker key 翻译成中文，未知时做一次可读化处理。"""
    if not tracker_key:
        return "未知数据"
    text = str(tracker_key).strip()
    lowered = text.lower()
    if lowered in TRACKER_NAMES:
        return TRACKER_NAMES[lowered]
    if text in TRACKER_NAMES:
        return TRACKER_NAMES[text]
    match = _SEASON_TRACKER_RE.match(lowered)
    if match:
        base_label = TRACKER_NAMES.get(match.group("base"))
        if base_label:
            return f"{base_label}（第{match.group('season')}赛季）"
    readable = text.replace("_", " ").replace("-", " ").strip()
    return readable.title() if readable else text
