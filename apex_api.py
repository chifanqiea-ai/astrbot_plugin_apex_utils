"""Mozambique Heirloom API（Apex Legends Status）异步客户端。

负责：
* 调用 ``/bridge.php`` 拉取玩家战绩，调用 ``/nametouid.php`` 把 EA ID 解析成 UID；
* 内存 + 磁盘两级缓存，降低 API 调用次数（免费额度约 2 次/秒）；
* 把各类异常统一转换为带中文文案的 :class:`ApexApiError`。

本模块不依赖 AstrBot 框架，可独立测试。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

try:  # AstrBot 以包形式加载插件时走相对导入
    from .apex_constants import (
        DATA_SOURCE_LABEL,
        DEFAULT_API_BASE,
        DEFAULT_PLATFORM,
        DIVISION_ROMAN,
        ERROR_MESSAGES,
        IGNORED_TRACKERS,
        PLATFORM_ALIASES,
        PLATFORMS,
        translate_legend,
        translate_rank,
        translate_tracker,
    )
except ImportError:  # pragma: no cover - 兼容以顶层模块方式加载
    from apex_constants import (  # type: ignore[no-redef]
        DATA_SOURCE_LABEL,
        DEFAULT_API_BASE,
        DEFAULT_PLATFORM,
        DIVISION_ROMAN,
        ERROR_MESSAGES,
        IGNORED_TRACKERS,
        PLATFORM_ALIASES,
        PLATFORMS,
        translate_legend,
        translate_rank,
        translate_tracker,
    )

try:  # httpx 是 AstrBot 自带依赖，缺失时退化到 aiohttp。
    import httpx
except ImportError:  # pragma: no cover - 取决于运行环境
    httpx = None  # type: ignore[assignment]

try:
    import aiohttp
except ImportError:  # pragma: no cover - 取决于运行环境
    aiohttp = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 平台解析
# ---------------------------------------------------------------------------


def normalize_platform(value: Any, default: str = DEFAULT_PLATFORM) -> str:
    """把用户输入的平台写法规范化为 API 平台值（PC/PS4/X1/SWITCH）。"""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    upper = text.upper()
    if upper in PLATFORMS:
        return upper
    return PLATFORM_ALIASES.get(text.lower(), "")


def platform_label(platform: str) -> str:
    """平台值的展示名。"""
    return PLATFORMS.get(platform, platform)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class ApexApiError(Exception):
    """API 调用失败，``user_message`` 可直接发给聊天用户。"""

    def __init__(self, code: str, message: str = "", user_message: str | None = None) -> None:
        self.code = code
        self.message = message
        if user_message is None:
            template = ERROR_MESSAGES.get(code, "❌ 查询失败：{message}")
            try:
                user_message = template.format(message=message)
            except (KeyError, IndexError):  # 模板里没有占位符
                user_message = template
        self.user_message = user_message
        super().__init__(f"[{code}] {message or code}")


# ---------------------------------------------------------------------------
# 数值工具
# ---------------------------------------------------------------------------


def to_int(value: Any) -> int:
    """尽力把 API 返回值转换成 int，失败返回 0。"""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def format_number(value: Any) -> str:
    """带千位分隔符的数字展示，非数字原样返回。"""
    if isinstance(value, bool) or value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{int(value):,}"
    text = str(value).strip()
    if not text:
        return "-"
    try:
        return f"{int(float(text.replace(',', ''))):,}"
    except ValueError:
        return text


def perfect_score(points: Any) -> int:
    """把 ``rankScore`` 字段还原成数值。

    ``/bridge`` 的 ``rankScore`` 是 ``{"rankedScore": int, "ladderScore": float}``
    形式的字典，个别版本会直接返回整数。
    """
    if isinstance(points, dict):
        for key in ("rankedScore", "ladderScore", "score", "value"):
            if key in points:
                return to_int(points[key])
        return 0
    return to_int(points)


# ---------------------------------------------------------------------------
# 响应解析
# ---------------------------------------------------------------------------


def _extract_overall(global_data: dict[str, Any]) -> dict[str, Any]:
    """解析全局统计（等级、总击杀、总伤害、场次等）。"""
    rank = global_data.get("rank") if isinstance(global_data.get("rank"), dict) else {}
    level = to_int(global_data.get("level"))
    if level <= 0:
        level = to_int(rank.get("rankedSeasonLevel"))

    return {
        "name": global_data.get("name") or global_data.get("uid") or "未知玩家",
        "uid": str(global_data.get("uid") or ""),
        "level": level,
        "prestige": to_int(global_data.get("levelPrestige")),
        "kills": to_int(global_data.get("kills")),
        "damage": to_int(global_data.get("damage")),
        "wins": to_int(global_data.get("wins")),
        "matches": to_int(global_data.get("matches")),
        "rp": perfect_score(rank.get("rankScore")),
        "rank_name": rank.get("rankName") or "",
        "rank_div": to_int(rank.get("rankDiv")),
        "rank_img": rank.get("rankImg") or "",
        "ladder": rank.get("ladderPosPlatform"),
        "platform": global_data.get("platform") or "",
        "bans": global_data.get("bans") if isinstance(global_data.get("bans"), dict) else {},
    }


def _tracker_value(item: Any) -> str:
    """取出数据卡的展示值。

    ``/bridge`` 的取值形态在不同版本/端点之间并不统一，需要全部兼容：
    * ``{"value": 1111, "name": "Kills"}``
    * ``{"kills": 958}``
    * ``1111`` / ``"1,111"``
    """
    if isinstance(item, dict):
        for key in ("value", "Value", "val"):
            if key in item:
                value = item[key]
                return format_number(value) if isinstance(value, (int, float)) else str(value)
        for key in ("kills", "damage", "wins", "matches", "games_played", "score"):
            if key in item:
                return format_number(item[key])
        return "-"
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return format_number(item)
    if item is None:
        return "-"
    return str(item)


def _collect_trackers(raw_data: Any) -> list[tuple[str, str]]:
    """把传奇数据卡统一成 ``[(key, 展示值)]`` 列表。

    兼容三种真实形态：
    * 数组：``[{"key": "kills", "value": 958}, ...]``
    * 字典：``{"kills": {"name": "Kills", "value": 958, "key": "kills"}}``
    * 展开的字典：``{"kills": 958, "damage": 254506}``
    """
    trackers: list[tuple[str, str]] = []
    if isinstance(raw_data, list):
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("name")
            if not key or str(key).lower() in IGNORED_TRACKERS:
                continue
            trackers.append((str(key), _tracker_value(item)))
    elif isinstance(raw_data, dict):
        for key, item in raw_data.items():
            if str(key).lower() in IGNORED_TRACKERS:
                continue
            trackers.append((str(key), _tracker_value(item)))
    return trackers


def _extract_selected(legends: dict[str, Any]) -> dict[str, Any] | None:
    """解析「当前赛季所选传奇」。

    ``legends.selected`` 在不同版本里有两种真实形态：
    * v5：``{"Lifeline": {"kills": 958, "damage": 254506, "ImgAssets": {...}}}``
    * 旧版：``{"LegendName": "Lifeline", "data": [...]}``
    """
    selected = legends.get("selected")
    if isinstance(selected, dict) and selected:
        # 旧版形态：对象内部带传奇名字段
        for name_field in ("legendName", "LegendName", "name"):
            candidate = selected.get(name_field)
            if isinstance(candidate, str) and candidate:
                raw_data = selected.get("data", selected)
                if isinstance(raw_data, dict):
                    raw_data = {k: v for k, v in raw_data.items() if k != name_field}
                icon = ""
                if isinstance(selected.get("ImgAssets"), dict):
                    icon = selected["ImgAssets"].get("icon", "")
                return {
                    "name": candidate,
                    "icon": icon,
                    "trackers": _collect_trackers(raw_data),
                }

        # v5 形态：传奇名作为键
        for name, payload in selected.items():
            if not isinstance(name, str) or not name:
                continue
            raw_data: Any = payload
            icon = ""
            if isinstance(payload, dict):
                icon = (
                    payload.get("ImgAssets", {}).get("icon", "") if isinstance(payload.get("ImgAssets"), dict) else ""
                )
                raw_data = payload.get("data", payload)
            trackers = _collect_trackers(raw_data)
            if trackers:
                return {"name": name, "icon": icon, "trackers": trackers}

    all_legends = legends.get("all")
    if isinstance(all_legends, list):
        for season in all_legends:
            if not isinstance(season, dict):
                continue
            name = season.get("legendName")
            if not name:
                continue
            icon = ""
            if isinstance(season.get("ImgAssets"), dict):
                icon = season["ImgAssets"].get("icon", "")
            return {
                "name": str(name),
                "icon": icon,
                "trackers": _collect_trackers(season.get("data")),
            }
    return None


def _extract_top_legends(legends: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """解析「常用传奇」：按数据卡数量/击杀数排序取前几名。"""
    all_legends = legends.get("all")
    if not isinstance(all_legends, list):
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for season in all_legends:
        if not isinstance(season, dict):
            continue
        name = season.get("legendName")
        if not name:
            continue
        trackers = _collect_trackers(season.get("data"))
        if not trackers:
            continue
        kills = 0
        for key, value in trackers:
            if str(key).lower() in ("kills", "br_kills", "season_kills"):
                kills = to_int(str(value).replace(",", ""))
                break
        scored.append((kills, {"name": str(name), "trackers": trackers}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[: max(0, limit)]]


#: ``_parse_uid`` 显式栈中表示「短路返回 UID」的哨兵。
#: 数据来自 json.loads，只会出现 dict/list/标量，不会与真实数据混淆。
_UID_SENTINEL = object()


def _parse_uid(payload: Any) -> str:
    """从 ``/nametouid`` 响应中取出 UID。

    该端点的响应形态在不同文档/版本之间不一致（``{"uid": ...}``、
    ``{"result": ...}``、``[{"uid": ...}]``、``{"data": {...}}``），
    这里统一做防御式解析。

    实现上用显式栈做深度优先遍历（而非递归）：若数据源返回的 JSON
    被构造为极深嵌套，递归写法会触发 RecursionError；显式栈不占用
    调用栈深度，任何深度的数据都能安全处理。
    """
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        # 哨兵项：表示该位置应短路返回 UID（对应递归版的 return）
        if isinstance(current, tuple) and len(current) == 2 and current[0] is _UID_SENTINEL:
            return current[1]
        if isinstance(current, list):
            stack.extend(reversed(current))  # 反向入栈，保持从左到右逐个尝试
            continue
        if not isinstance(current, dict):
            continue

        # 展开当前 dict 的候选序列，顺序与递归版一致：
        # 先查 uid/result/value/id 四个键；值是 dict 时优先深入，
        # 值是标量且非空时短路返回；四个键都没有结果再深入
        # data/player/players/items 四个键。
        deferred: list[Any] = []
        for key in ("uid", "result", "value", "id"):
            value = current.get(key)
            if isinstance(value, dict):
                deferred.append(value)  # 深入；解析为空时继续后续候选
            elif value is not None and str(value).strip():
                deferred.append((_UID_SENTINEL, str(value).strip()))
                break  # 短路：递归版此处直接 return
        if not deferred or not (isinstance(deferred[-1], tuple) and deferred[-1][0] is _UID_SENTINEL):
            for key in ("data", "player", "players", "items"):
                if key in current:
                    deferred.append(current[key])
        stack.extend(reversed(deferred))
    return ""


def _normalize_total(raw_total: Any) -> dict[str, Any]:
    """把 ``total`` 端点统一成 ``{key: 展示值字符串}``。"""
    normalized: dict[str, Any] = {}
    if isinstance(raw_total, dict):
        for key, item in raw_total.items():
            if str(key).lower() in IGNORED_TRACKERS:
                continue
            normalized[str(key)] = _tracker_value(item)
    return normalized


def parse_player_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把 ``/bridge`` 的原始响应整理成插件内部使用的结构。"""
    global_data = payload.get("global")
    if not isinstance(global_data, dict) or not global_data:
        raise ApexApiError("EMPTY_RESULT")

    raw_total = payload.get("total") if isinstance(payload.get("total"), dict) else {}
    normalized_total = _normalize_total(raw_total)
    overall = _extract_overall(global_data)
    if overall["matches"] <= 0:
        overall["matches"] = to_int(str(normalized_total.get("games_played", "0")).replace(",", ""))
    if overall["kills"] <= 0:
        overall["kills"] = to_int(str(normalized_total.get("kills", "0")).replace(",", ""))
    if overall["damage"] <= 0:
        overall["damage"] = to_int(str(normalized_total.get("damage", "0")).replace(",", ""))
    if overall["wins"] <= 0:
        overall["wins"] = to_int(str(normalized_total.get("wins", "0")).replace(",", ""))

    realtime = payload.get("realtime") if isinstance(payload.get("realtime"), dict) else {}

    legends = payload.get("legends") if isinstance(payload.get("legends"), dict) else {}
    return {
        "overall": overall,
        "legend": _extract_selected(legends),
        "top_legends": _extract_top_legends(legends),
        "trackers": normalized_total,
        "realtime": realtime,
        "raw": payload,
    }


# ---------------------------------------------------------------------------
# 文案渲染
# ---------------------------------------------------------------------------


def _format_rank_name(rank_name: str, rank_div: int) -> str:
    label = translate_rank(rank_name)
    if rank_div:
        return f"{label} {DIVISION_ROMAN.get(rank_div, str(rank_div))}"
    return label


def format_player_text(
    data: dict[str, Any],
    platform: str,
    max_trackers: int = 8,
    preferred_trackers: tuple[str, ...] = (),
    ignored_trackers: frozenset[str] = frozenset(),
    max_legends: int = 3,
) -> str:
    """把解析后的玩家数据渲染成中文战绩文案。"""
    overall = data.get("overall") or {}
    lines: list[str] = []
    lines.append(f"【{overall.get('name', '未知玩家')}】Apex Legends 战绩")
    lines.append(f"平台：{platform_label(platform)}")
    lines.append("━━━━━━━━━━━━━━")

    # 等级 / 段位
    level_text = f"Lv.{overall.get('level', 0)}"
    prestige = overall.get("prestige") or 0
    if prestige:
        level_text += f"（威望 {prestige}）"
    rank_text = _format_rank_name(overall.get("rank_name", ""), overall.get("rank_div") or 0)
    rp = overall.get("rp") or 0
    if rp:
        rank_text += f"｜{rp:,} RP"
    ladder = to_int(overall.get("ladder"))
    if ladder > 0:  # API 用 -1 表示未上榜，此时不显示名次
        rank_text += f"｜平台第 {ladder} 名"
    lines.append(f"等级：{level_text}")
    lines.append(f"段位：{rank_text}")

    bans = overall.get("bans") or {}
    if bans.get("isActive"):
        lines.append("⚠️ 该账号当前处于封禁状态")

    # 生涯总览
    kills = overall.get("kills") or 0
    damage = overall.get("damage") or 0
    wins = overall.get("wins") or 0
    matches = overall.get("matches") or 0
    if kills or damage or wins or matches:
        lines.append("")
        lines.append("── 生涯总览 ──")
        if kills:
            lines.append(f"总击杀：{kills:,}")
        if damage:
            lines.append(f"总伤害：{damage:,}")
        if wins:
            lines.append(f"总胜场：{wins:,}")
        if matches:
            lines.append(f"总场次：{matches:,}")
        if matches and wins:
            lines.append(f"胜率：{wins / matches * 100:.1f}%")
        if matches and kills:
            lines.append(f"场均击杀：{kills / matches:.2f}")

    # 数据卡（tracker）；``total.kd.value == -1`` 表示数据不足，直接跳过
    trackers = data.get("trackers") or {}
    if isinstance(trackers, dict) and trackers:
        rows: list[tuple[str, str]] = []
        used: set[str] = set()
        for key in preferred_trackers:
            if key in trackers and key.lower() not in ignored_trackers:
                rows.append((key, str(trackers[key])))
                used.add(key)
        for key, value in trackers.items():
            if len(rows) >= max_trackers:
                break
            if key in used or key.lower() in ignored_trackers:
                continue
            rows.append((key, str(value)))
        rendered: list[str] = []
        for key, value in rows[:max_trackers]:
            if str(key).lower() in ("kd", "kd_ratio", "kdr") and to_int(str(value).replace(",", "")) < 0:
                continue  # -1 代表官方数据不足
            rendered.append(f"{translate_tracker(key)}：{value}")
        if rendered:
            lines.append("")
            lines.append("── 数据卡 ──")
            lines.extend(rendered)

    # 当前传奇
    legend = data.get("legend")
    if legend:
        lines.append("")
        lines.append(f"── 当前传奇：{translate_legend(legend.get('name'))} ──")
        trackers_of_legend = legend.get("trackers") or []
        if trackers_of_legend:
            for key, value in trackers_of_legend:
                lines.append(f"{translate_tracker(key)}：{value}")
        else:
            lines.append("该传奇暂无公开数据卡")

    # 常用传奇（按击杀数排序的前几名）
    top_legends = data.get("top_legends") or []
    if max_legends > 0 and len(top_legends) > 1:
        lines.append("")
        lines.append("── 常用传奇 ──")
        for entry in top_legends[:max_legends]:
            parts = [
                f"{translate_tracker(key)} {value}"
                for key, value in (entry.get("trackers") or [])
                if str(key).lower() in ("kills", "damage", "wins", "games_played", "matches")
            ]
            detail = "｜".join(parts) if parts else "暂无数据"
            lines.append(f"{translate_legend(entry.get('name'))}：{detail}")

    lines.append("━━━━━━━━━━━━━━")
    lines.append(DATA_SOURCE_LABEL)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class ApexApiClient:
    """Mozambique Heirloom API 客户端（含缓存）。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = DEFAULT_API_BASE,
        timeout: float = 15.0,
        cache_ttl: int = 300,
        cache_path: Path | None = None,
        logger: Any = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or DEFAULT_API_BASE).strip().rstrip("/")
        self.timeout = max(3.0, float(timeout))
        self.cache_ttl = max(0, int(cache_ttl))
        self.cache_path = Path(cache_path) if cache_path else None
        self.logger = logger

        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._disk: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._uid_map: dict[str, str] = {}
        self._name_index: dict[str, str] = {}
        self._min_interval = 1.05  # 秒；默认按 1 次/秒保守节流
        self._next_allowed = 0.0
        self._load_cache()

    # -- 配置 ---------------------------------------------------------------

    def update_config(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        """配置热更新。"""
        if api_key is not None:
            self.api_key = api_key.strip()
        if base_url:
            self.base_url = base_url.strip().rstrip("/")
        if timeout is not None:
            self.timeout = max(3.0, float(timeout))
        if cache_ttl is not None:
            self.cache_ttl = max(0, int(cache_ttl))

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    # -- 缓存 ---------------------------------------------------------------

    def _load_cache(self) -> None:
        if not self.cache_path or not self.cache_path.exists():
            return
        try:
            with self.cache_path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
            if isinstance(payload, dict):
                players = payload.get("players")
                if isinstance(players, dict):
                    self._disk = {k: v for k, v in players.items() if isinstance(v, dict)}
                uid_map = payload.get("uid_map")
                if isinstance(uid_map, dict):
                    self._uid_map = {str(k): str(v) for k, v in uid_map.items()}
                name_index = payload.get("name_index")
                if isinstance(name_index, dict):
                    self._name_index = {str(k): str(v) for k, v in name_index.items()}
        except (OSError, ValueError) as exc:  # 缓存损坏不影响主流程
            self._log("warning", f"读取缓存失败，已忽略：{exc}")
            self._disk = {}

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": int(time.time()),
                "players": self._disk,
                "uid_map": self._uid_map,
                "name_index": self._name_index,
            }
            tmp_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
            tmp_path.replace(self.cache_path)
        except OSError as exc:
            self._log("warning", f"写入缓存失败，已忽略：{exc}")

    def _cache_key(self, platform: str, identity: str) -> str:
        return f"{platform}:{identity.lower()}"

    def _get_cached(self, key: str) -> tuple[dict[str, Any], float] | None:
        """返回 ``(数据, 缓存年龄秒数)``，未命中返回 None。"""
        now = time.time()
        hit = self._memory.get(key)
        if hit and now - hit[0] <= self.cache_ttl:
            return hit[1], now - hit[0]
        entry = self._disk.get(key)
        if entry:
            saved_at = to_int(entry.get("saved_at"))
            data = entry.get("data")
            if isinstance(data, dict) and now - saved_at <= self.cache_ttl:
                self._memory[key] = (saved_at, data)
                return data, now - saved_at
        return None

    def _get_stale(self, key: str) -> dict[str, Any] | None:
        """API 不可用时使用的过期缓存。"""
        entry = self._disk.get(key)
        data = entry.get("data") if entry else None
        return data if isinstance(data, dict) else None

    def _put_cached(self, key: str, data: dict[str, Any]) -> None:
        now = time.time()
        self._memory[key] = (now, data)
        self._disk[key] = {"saved_at": int(now), "data": data}
        overall = data.get("overall") or {}
        uid = overall.get("uid")
        name = overall.get("name")
        platform = overall.get("platform") or key.split(":", 1)[0]
        if uid:
            self._name_index[f"{platform}:{str(name).lower()}"] = str(uid)
        self._save_cache()

    # -- HTTP ---------------------------------------------------------------

    def _log(self, level: str, message: str) -> None:
        if self.logger is not None:
            getattr(self.logger, level, self.logger.info)(message)

    async def _throttle(self) -> None:
        """全局串行 + 最小间隔，避免触发数据源限流。"""
        async with self._lock:
            now = time.time()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.time()
            self._next_allowed = now + self._min_interval

    def note_response(self, headers: Any) -> None:
        """根据响应头自适应调整最小请求间隔。

        ``X-Current-Rate`` 形如 ``1;5``，第二个数字是每秒允许的请求数。
        """
        if not headers:
            return
        try:
            raw = headers.get("X-Current-Rate") or headers.get("x-current-rate")
        except AttributeError:
            return
        if not raw:
            return
        text = str(raw)
        if ";" in text:
            text = text.split(";", 1)[1]
        allowed = to_int(text.strip())
        if allowed > 0:
            self._min_interval = max(1.05, 1.0 / allowed + 0.05)

    async def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        """发起 GET 请求并处理错误码，返回解析后的 JSON。"""
        query = {k: v for k, v in params.items() if v is not None}
        query["auth"] = self.api_key
        url = f"{self.base_url}/{endpoint.lstrip('/')}.php"
        # 该站由 Apache 做内容协商：请求不带 .php 后缀的路径会被拦成 406，
        # 直接请求真实的 PHP 文件地址即可绕过（实测两个官方入口均可用）。
        headers = {
            "User-Agent": "AstrBot-ApexStats/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            # 新旧两种认证方式同时发送，兼容不同入口。
            headers["Authorization"] = self.api_key

        await self._throttle()
        try:
            status, text = await self._fetch(url, query, headers)
        except TimeoutError as exc:
            raise ApexApiError("TIMEOUT") from exc
        except ApexApiError:
            raise
        except Exception as exc:
            raise ApexApiError("NETWORK", str(exc)) from exc

        if status == 401 or status == 403:
            raise ApexApiError("INVALID_API_KEY")
        if status == 406:
            raise ApexApiError("API_ERROR", "数据源拒绝了请求（HTTP 406），请确认 api_base 配置正确")
        if status == 404:
            raise ApexApiError("NOT_FOUND")
        if status == 410:
            raise ApexApiError("UNKNOWN_PLATFORM")
        if status == 429:
            self._next_allowed = time.time() + 2.0  # 触发限流时退避
            raise ApexApiError("RATE_LIMITED")
        if status >= 400:
            detail = text.strip()[:200]
            if "API key" in detail or "Unauthorized" in detail:
                raise ApexApiError("INVALID_API_KEY")
            if "player" in detail.lower() and "not found" in detail.lower():
                raise ApexApiError("NOT_FOUND")
            raise ApexApiError("API_ERROR", f"HTTP {status} {detail}")

        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise ApexApiError("API_ERROR", f"响应不是合法 JSON：{text.strip()[:120]}") from exc

        if isinstance(payload, dict):
            error = payload.get("Error") or payload.get("error")
            if error:
                message = str(error)
                lowered = message.lower()
                if "api key" in lowered or "authorization" in lowered or lowered == "auth":
                    raise ApexApiError("INVALID_API_KEY")
                if "not found" in lowered or "player not found" in lowered:
                    raise ApexApiError("NOT_FOUND")
                if "rate" in lowered and "limit" in lowered:
                    raise ApexApiError("RATE_LIMITED")
                if "platform" in lowered:
                    raise ApexApiError("UNKNOWN_PLATFORM")
                raise ApexApiError("API_ERROR", message)
            if isinstance(payload.get("data"), dict) and payload.get("data"):
                payload = payload["data"]
        elif isinstance(payload, list):
            payload = {"data": payload}

        return payload

    async def _fetch(self, url: str, params: dict[str, Any], headers: dict[str, str]) -> tuple[int, str]:
        """优先用 httpx，其次 aiohttp，最后退化到标准库 urllib。

        三种实现的行为对外完全一致，插件不强制依赖第三方 HTTP 库。
        """
        if httpx is not None:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)
                self.note_response(response.headers)
                return response.status_code, response.text
        if aiohttp is not None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(url, params=params, headers=headers) as response,
            ):
                self.note_response(response.headers)
                return response.status, await response.text()
        return await asyncio.to_thread(self._fetch_urllib, url, params, headers)

    def _fetch_urllib(self, url: str, params: dict[str, Any], headers: dict[str, str]) -> tuple[int, str]:
        """标准库兜底实现（在线程中执行，避免阻塞事件循环）。"""
        import urllib.error
        import urllib.parse
        import urllib.request

        full_url = f"{url}?{urllib.parse.urlencode(params)}" if params else url
        request = urllib.request.Request(full_url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self.note_response(dict(response.headers))
                charset = response.headers.get_content_charset() or "utf-8"
                return response.status, response.read().decode(charset, "replace")
        except urllib.error.HTTPError as exc:
            self.note_response(dict(exc.headers or {}))
            charset = (exc.headers.get_content_charset() if exc.headers else None) or "utf-8"
            return exc.code, exc.read().decode(charset, "replace")

    # -- 业务接口 -----------------------------------------------------------

    async def name_to_uid(self, player: str, platform: str) -> str:
        """把 EA ID 解析成 UID；失败返回空字符串（不抛业务异常）。"""
        key = f"{platform}:{player.strip().lower()}"
        cached = self._name_index.get(key) or self._uid_map.get(key)
        if cached:
            return cached
        try:
            payload = await self._request("nametouid", {"player": player, "platform": platform, "version": 5})
        except ApexApiError as exc:
            self._log("debug", f"nametouid 解析失败（{exc.code}），将继续按名字查询")
            return ""
        uid = _parse_uid(payload)
        if uid:
            self._uid_map[key] = uid
            self._save_cache()
        return uid

    async def fetch_player(
        self,
        player: str,
        platform: str = DEFAULT_PLATFORM,
        use_cache: bool = True,
        retry_with_uid: bool = True,
    ) -> tuple[dict[str, Any], bool, float | None]:
        """查询玩家战绩。

        返回 ``(解析后的数据, 是否命中缓存, 缓存年龄秒数)``。

        查询顺序：
        1. 命中缓存 → 直接返回；
        2. 若已知该 EA ID 对应的 UID，则优先用 UID 查询（改名后依然有效）；
        3. 用名字查询；若失败则通过 ``/nametouid`` 解析 UID 后重试一次。
        """
        platform = normalize_platform(platform)
        if not platform:
            raise ApexApiError("UNKNOWN_PLATFORM")
        if not self.has_api_key:
            raise ApexApiError("NO_API_KEY")

        identity = (player or "").strip()
        if not identity:
            raise ApexApiError("NOT_FOUND")

        name_key = self._cache_key(platform, identity)
        if use_cache:
            cached = self._get_cached(name_key)
            if cached is not None:
                data, age = cached
                return data, True, age

        known_uid = self._name_index.get(name_key) or self._uid_map.get(name_key)
        errors: list[ApexApiError] = []

        async def _try_uid(uid: str) -> dict[str, Any]:
            payload = await self._request(
                "bridge",
                {"uid": uid, "platform": platform, "version": 5, "merge": 1},
            )
            if not isinstance(payload, dict) or not payload.get("global"):
                raise ApexApiError("NOT_FOUND")
            return parse_player_payload(payload)

        async def _try_name(name: str) -> dict[str, Any]:
            payload = await self._request(
                "bridge",
                {"player": name, "platform": platform, "version": 5, "merge": 1},
            )
            if not isinstance(payload, dict) or not payload.get("global"):
                raise ApexApiError("NOT_FOUND")
            return parse_player_payload(payload)

        async def _store(requested_uid: str, data: dict[str, Any]) -> tuple[dict[str, Any], bool, float | None]:
            # 把响应里的真实 UID 一并缓存：玩家改名后依然可以直接用 UID 查询
            real_uid = str((data.get("overall") or {}).get("uid") or "").strip()
            if not real_uid:
                real_uid = requested_uid
            self._put_cached(name_key, data)
            if real_uid:
                self._uid_map[name_key] = real_uid
                self._put_cached(self._cache_key(platform, real_uid), data)
            return data, False, None

        data: dict[str, Any] | None = None
        uid_input = identity if identity.isdigit() else ""

        # 1) 已知 UID 优先（玩家改名后依然有效）
        if known_uid and not uid_input:
            try:
                return await _store(known_uid, await _try_uid(known_uid))
            except ApexApiError as exc:
                errors.append(exc)

        # 2) 直接给的是 UID
        if uid_input:
            try:
                return await _store(uid_input, await _try_uid(uid_input))
            except ApexApiError as exc:
                errors.append(exc)

        # 3) 用 EA ID（显示名）查询
        try:
            data = await _try_name(identity)
        except ApexApiError as exc:
            errors.append(exc)
            data = None

        # 4) 名字查询失败时，先解析成 UID 再试一次
        if data is None and retry_with_uid and not uid_input:
            resolved = await self.name_to_uid(identity, platform)
            if resolved:
                try:
                    data = await _try_uid(resolved)
                except ApexApiError as exc:
                    errors.append(exc)
                    data = None
                if data is not None:
                    return await _store(resolved, data)

        if data is not None:
            return await _store("", data)

        # 全部失败：优先抛出「找不到玩家」，否则抛出最后一个错误；再兜底过期缓存。
        not_found = next((e for e in errors if e.code == "NOT_FOUND"), None)
        final_error = not_found or (errors[-1] if errors else ApexApiError("API_ERROR", "未知错误"))
        stale = self._get_stale(name_key)
        if stale is not None and final_error.code in ("TIMEOUT", "NETWORK", "API_ERROR", "RATE_LIMITED"):
            self._log("warning", f"API 不可用（{final_error.code}），使用过期缓存返回")
            return stale, True, None
        raise final_error

    # -- 维护 ---------------------------------------------------------------

    def clear_cache(self) -> int:
        """清空缓存，返回清理的条目数。"""
        count = len(self._disk)
        self._memory.clear()
        self._disk.clear()
        self._uid_map.clear()
        self._name_index.clear()
        self._save_cache()
        return count
