"""AstrBot 插件：通过指令查询 Apex Legends 玩家战绩。

指令一览：
* ``/apex <EA ID> [平台]``   查询指定玩家战绩
* ``/apex bind <EA ID>``     绑定自己的 EA ID（之后可直接 ``/apex``）
* ``/apex unbind``           解除绑定
* ``/apex help``             查看帮助
* ``/apex clearcache``       清空本地缓存

数据来源：Mozambique Heirloom API（api.mozambiquehe.re / apexlegendsstatus.com）。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

try:  # 相对导入（AstrBot 正常加载插件时）
    from .apex_api import (
        ApexApiClient,
        ApexApiError,
        format_player_text,
        normalize_platform,
        platform_label,
        to_int,
    )
    from .apex_constants import (
        DEFAULT_API_BASE,
        DEFAULT_PLATFORM,
        IGNORED_TRACKERS,
        MAX_TRACKER_ROWS,
        PREFERRED_TRACKERS,
    )
except ImportError:  # pragma: no cover - 兼容以顶层模块方式加载
    from apex_api import (  # type: ignore[no-redef]
        ApexApiClient,
        ApexApiError,
        format_player_text,
        normalize_platform,
        platform_label,
        to_int,
    )
    from apex_constants import (  # type: ignore[no-redef]
        DEFAULT_API_BASE,
        DEFAULT_PLATFORM,
        IGNORED_TRACKERS,
        MAX_TRACKER_ROWS,
        PREFERRED_TRACKERS,
    )

PLUGIN_NAME = "astrbot_plugin_apex_stats"
CACHE_FILENAME = "apex_cache.json"
BINDINGS_FILENAME = "apex_bindings.json"
SHORT_TTL = 30  # 秒，缓存命中时的提示阈值

HELP_TEXT = """🎮 Apex Legends 战绩查询 · 使用说明

▸ /apex <EA ID> [平台]
  查询指定玩家的战绩，例如：
    /apex MyOriginID
    /apex MyOriginID ps
  平台可省略（默认配置的平台），可选值：
    pc（EA/Origin，含 Steam 玩家）/ ps / xbox / switch

▸ /apex
  直接查询自己已绑定的 EA ID。

▸ /apex bind <EA ID> [平台]
  绑定自己的 EA ID，之后直接发 /apex 即可查询。

▸ /apex unbind
  解除自己的绑定。

▸ /apex clearcache
  清空本地查询缓存（管理员）。

▸ /apex help
  显示本帮助。

📌 说明
· PC 平台请填 EA / Origin 账号名（Steam 玩家的 Steam 昵称不可用）。
· 昵称含空格时建议使用绑定命令，或直接用 UID 查询。
· 数据来源：Mozambique Heirloom API，非官方接口，仅供参考。"""


# ---------------------------------------------------------------------------
# 插件数据目录
# ---------------------------------------------------------------------------


def _resolve_data_dir() -> Path:
    """尽量使用 AstrBot 的插件数据目录，失败则退化到插件目录下的 data/。

    持久化数据必须放在 ``data/plugin_data/`` 下而不是插件自身目录，
    否则插件更新/重装时数据会被覆盖。
    """
    try:
        from astrbot.core.star.star_tools import StarTools  # type: ignore

        return Path(StarTools.get_data_dir(PLUGIN_NAME))
    except Exception as exc:  # noqa: BLE001 - 不同版本接口不一致
        logger.debug(f"[Apex] 无法通过 astrbot.core.star 获取数据目录：{exc}")
    try:
        from astrbot.api.star import StarTools  # type: ignore

        return Path(StarTools.get_data_dir(PLUGIN_NAME))
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[Apex] 无法通过 astrbot.api.star 获取数据目录：{exc}")
    return Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------


def _strip_command(message_str: str, commands: tuple[str, ...] = ("apex",)) -> str:
    """去掉唤醒前缀与指令名，只保留参数部分。

    ``event.message_str`` 在不同触发方式下形态不同：
    私聊/被 @ 时可能没有 ``/`` 前缀，且指令名仍在字符串里，因此两者都要处理。
    例如 ``/apex MyID`` 与 ``apex MyID`` 都应解析出 ``MyID``。
    """
    text = (message_str or "").strip()
    if not text:
        return ""
    if text.startswith("/"):
        text = text[1:].lstrip()

    lowered = text.lower()
    for name in sorted(commands, key=len, reverse=True):
        token = name.lower()
        if lowered == token:
            return ""
        if lowered.startswith(token) and len(text) > len(name) and text[len(name)].isspace():
            return text[len(name) :].strip()

    # 兜底：当成「指令 参数」的形式，丢掉第一个词
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return ""
    return parts[1].strip()


def _command_alias() -> dict[str, Any]:
    """返回指令别名参数。

    ⚠️ 指令别名必须通过 ``@filter.command`` 的 ``alias`` 参数提供：
    在同一个函数上叠加多个 ``@filter.command`` 装饰器会注册出多个
    ``CommandFilter``，而过滤器之间是 AND 关系，指令会因此完全失效。
    """
    return {"alias": {"Apex", "APEX", "查询战绩", "查战绩"}}


def _parse_query_args(raw: str, default_platform: str) -> tuple[str, str, str]:
    """解析查询参数。

    返回 ``(player, platform, error)``，``error`` 非空时表示参数有误。
    支持的写法：
    * ``玩家ID``
    * ``玩家ID pc``
    * ``pc 玩家ID``
    * ``玩家ID 平台:pc``
    """
    text = (raw or "").strip()
    if not text:
        return "", default_platform, ""

    tokens = text.split()
    platform = default_platform
    platform_set = False
    invalid_platform = ""
    player_parts: list[str] = []

    for index, token in enumerate(tokens):
        lowered = token.strip().lower()
        explicit = lowered.startswith(("平台:", "platform:"))
        if explicit:
            lowered = lowered.split(":", 1)[1]
        resolved = normalize_platform(lowered, default="")

        # 仅在这几种情况下才把 token 当作平台参数，避免把名叫 pc / ps 的玩家误判：
        #   · 显式写法「平台:pc」
        #   · 平台写在玩家名之前且后面还有内容（pc shroud）
        #   · 平台写在末尾且前面已经有玩家名（shroud pc）
        is_last = index == len(tokens) - 1
        is_first = index == 0
        if explicit:
            if not platform_set:
                platform_set = True
                if resolved:
                    platform = resolved
                else:
                    invalid_platform = lowered  # 写了「平台:xxx」但 xxx 不认识
            else:
                player_parts.append(token)
            continue
        if resolved and not platform_set:
            if is_first and len(tokens) > 1:
                platform = resolved
                platform_set = True
                continue
            if is_last and player_parts:
                platform = resolved
                platform_set = True
                continue
        player_parts.append(token)

    player = " ".join(player_parts).strip()
    if not player:
        return "", platform, "empty"
    if invalid_platform:
        return player, platform, "platform"
    if not platform:
        return player, default_platform, "platform"
    return player, platform, ""


def _format_relative_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒前"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    return f"{seconds // 3600} 小时前"


# ---------------------------------------------------------------------------
# 插件主体
# ---------------------------------------------------------------------------


@register(
    PLUGIN_NAME,
    "Miaoyww",
    "通过指令按 EA ID 查询 Apex Legends 玩家战绩（等级/段位/击杀/当前传奇），支持段位图标。",
    "1.0.0",
    "https://github.com/example/astrbot_plugin_apex_stats",
)
class ApexStatsPlugin(Star):
    """Apex Legends 战绩查询插件。"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        """初始化插件。

        插件目录带有 ``_conf_schema.json``，AstrBot 会注入 ``config``；
        这里保留默认值，兼容加载器不注入配置的情况。
        """
        super().__init__(context)
        self.config: Any = config if config is not None else {}
        self.data_dir = _resolve_data_dir()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover
            logger.warning(f"[Apex] 无法创建数据目录 {self.data_dir}：{exc}")

        self.client = ApexApiClient(
            api_key=self._conf("api_key", ""),
            base_url=self._conf("api_base", DEFAULT_API_BASE),
            timeout=self._conf("request_timeout", 15),
            cache_ttl=self._conf("cache_ttl", 300),
            cache_path=self.data_dir / CACHE_FILENAME,
            logger=logger,
        )
        self._bindings: dict[str, Any] = self._load_json(self.data_dir / BINDINGS_FILENAME, {})
        self._bind_lock = asyncio.Lock()
        logger.info(
            f"[Apex] 插件已加载｜数据目录：{self.data_dir}｜"
            f"API Key：{'已配置' if self.client.has_api_key else '未配置'}"
        )

    # -- 配置 / 持久化 ------------------------------------------------------

    def _conf(self, key: str, default: Any = None) -> Any:
        """安全读取配置项（兼容 config 为 dict 或 AstrBotConfig）。

        注意：调用方对布尔开关请传 ``default=None`` 再显式判空，
        否则用户把开关设为 ``false`` 时会被误判成「未配置」而回退默认值。
        AstrBot 会依据 ``_conf_schema.json`` 补齐默认值，因此多数情况下
        这里读到的都是用户真实配置。
        """
        try:
            value = self.config.get(key, default)
        except AttributeError:
            value = getattr(self.config, key, default)
        if value is None:
            return default
        if isinstance(value, str) and not value.strip() and default:
            return default  # 空字符串视作未配置
        return value

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as fp:
                return json.load(fp)
        except (OSError, ValueError) as exc:
            logger.warning(f"[Apex] 读取 {path.name} 失败，已重置：{exc}")
            return default

    @staticmethod
    def _save_json(path: Path, payload: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as exc:
            logger.warning(f"[Apex] 写入 {path.name} 失败：{exc}")

    def _binding_key(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id())
        except Exception:  # noqa: BLE001 - 个别适配器可能没有发送者信息
            return ""

    def _get_binding(self, event: AstrMessageEvent) -> dict[str, str]:
        key = self._binding_key(event)
        if not key:
            return {}
        entry = self._bindings.get(key)
        return entry if isinstance(entry, dict) else {}

    def _set_binding(self, event: AstrMessageEvent, player: str, platform: str) -> bool:
        key = self._binding_key(event)
        if not key:
            return False
        self._bindings[key] = {
            "player": player,
            "platform": platform,
            "updated_at": int(time.time()),
        }
        self._save_json(self.data_dir / BINDINGS_FILENAME, self._bindings)
        return True

    def _remove_binding(self, event: AstrMessageEvent) -> bool:
        key = self._binding_key(event)
        if key and key in self._bindings:
            self._bindings.pop(key, None)
            self._save_json(self.data_dir / BINDINGS_FILENAME, self._bindings)
            return True
        return False

    # -- 渲染 ---------------------------------------------------------------

    def _build_chain(self, data: dict[str, Any], platform: str) -> list[Any]:
        """构造回复消息链：段位图标 + 文本战绩。"""
        chain: list[Any] = []
        rank_img = ((data.get("overall") or {}).get("rank_img") or "").strip()
        enable_image = self._conf("enable_rank_image", None)
        if enable_image is None:
            enable_image = True  # schema 未生效时的默认行为
        if enable_image and rank_img.startswith("http"):
            try:
                chain.append(Image.fromURL(rank_img))
            except Exception as exc:  # noqa: BLE001 - 图片组件构造失败不影响文本
                logger.debug(f"[Apex] 构造段位图标失败：{exc}")

        text = format_player_text(
            data,
            platform=platform,
            max_trackers=to_int(self._conf("max_trackers", MAX_TRACKER_ROWS)) or MAX_TRACKER_ROWS,
            preferred_trackers=PREFERRED_TRACKERS,
            ignored_trackers=IGNORED_TRACKERS,
        )
        chain.append(Plain(text))
        return chain

    @staticmethod
    def _cached_hint(age: float | None) -> str:
        """缓存命中提示。"""
        if age is None:
            return "\n⚡ 数据源暂时不可用，以上为本地缓存的最近一次结果"
        if age <= SHORT_TTL:
            return "\n⚡ 由于刚查过，本次为本地缓存结果"
        return f"\n⚡ 缓存结果（{_format_relative_time(age)}获取）"

    # -- 指令 ---------------------------------------------------------------

    @filter.command("apex", **_command_alias())
    async def apex_handler(self, event: AstrMessageEvent):
        """Apex 战绩查询主指令。"""
        raw = _strip_command(event.message_str)
        default_platform = str(self._conf("default_platform", DEFAULT_PLATFORM) or DEFAULT_PLATFORM)

        if not raw:
            binding = self._get_binding(event)
            player = str(binding.get("player", "")).strip()
            platform = str(binding.get("platform", "") or default_platform)
            if not player:
                yield event.plain_result(
                    "请输入要查询的 EA ID，例如：\n"
                    "  /apex MyOriginID\n"
                    "或先绑定自己的账号：\n"
                    "  /apex bind MyOriginID\n\n"
                    "发送 /apex help 查看完整说明。"
                )
                return
        else:
            # 子命令：bind / unbind / help / clearcache
            head = raw.split(maxsplit=1)[0].lower()
            if head in ("help", "h", "帮助", "?", "？"):
                yield event.plain_result(HELP_TEXT)
                return
            if head in ("bind", "绑定"):
                rest = _strip_command(raw, ("bind", "绑定"))
                async for result in self._cmd_bind(event, rest, default_platform):
                    yield result
                return
            if head in ("unbind", "解绑", "解除绑定"):
                async for result in self._cmd_unbind(event):
                    yield result
                return
            if head in ("clearcache", "清空缓存", "clear"):
                async for result in self._cmd_clear_cache(event):
                    yield result
                return

            player, platform, error = _parse_query_args(raw, default_platform)
            if error == "platform":
                yield event.plain_result("❌ 未知平台。可用平台：pc / ps / xbox / switch\n例如：/apex MyOriginID ps")
                return
            if not player:
                yield event.plain_result("❌ 请提供要查询的 EA ID。发送 /apex help 查看用法。")
                return

        # 执行查询
        try:
            data, cached, cache_age = await self.client.fetch_player(player, platform)
        except ApexApiError as exc:
            logger.info(f"[Apex] 查询失败｜player={player}｜platform={platform}｜{exc}")
            yield event.plain_result(exc.user_message)
            return
        except Exception as exc:  # noqa: BLE001 - 兜底，避免插件抛错刷屏
            logger.error(f"[Apex] 查询异常｜player={player}｜platform={platform}｜{exc}", exc_info=True)
            yield event.plain_result(f"❌ 查询出现未预期的错误：{exc}")
            return

        chain = self._build_chain(data, platform)
        show_hint = self._conf("show_cache_hint", None)
        if cached and (show_hint is None or show_hint):
            chain[-1] = Plain(chain[-1].text + self._cached_hint(cache_age))
        yield event.chain_result(chain)

    async def _cmd_bind(self, event: AstrMessageEvent, rest: str, default_platform: str):
        """绑定：/apex bind <EA ID> [平台]"""
        player, platform, error = _parse_query_args(rest, default_platform)
        if error or not player:
            yield event.plain_result("用法：/apex bind <EA ID> [平台]\n例如：/apex bind MyOriginID pc")
            return
        if not self._set_binding(event, player, platform):
            yield event.plain_result("❌ 无法获取你的用户标识，绑定失败。")
            return
        yield event.plain_result(
            f"✅ 绑定成功！\nEA ID：{player}\n平台：{platform_label(platform)}\n之后直接发送 /apex 即可查询。"
        )

    async def _cmd_unbind(self, event: AstrMessageEvent):
        if self._remove_binding(event):
            yield event.plain_result("✅ 已解除绑定。")
        else:
            yield event.plain_result("你还没有绑定 EA ID，可发送 /apex bind <EA ID> 进行绑定。")

    async def _cmd_clear_cache(self, event: AstrMessageEvent):
        count = self.client.clear_cache()
        yield event.plain_result(f"✅ 已清空本地缓存，共清理 {count} 条玩家数据。")

    # -- 生命周期 -----------------------------------------------------------

    async def terminate(self):
        """插件卸载/重载时保存缓存。"""
        try:
            self.client._save_cache()
            self._save_json(self.data_dir / BINDINGS_FILENAME, self._bindings)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Apex] 退出前保存数据失败：{exc}")
