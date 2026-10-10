"""用最小 AstrBot mock 驱动 main.py，验证指令解析、绑定、图片链与错误提示。

不需要真实 AstrBot 环境，也不联网（网络层被替换为假客户端）。
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    for module_name in list(sys.modules):
        if module_name == "main" or module_name.startswith(("apex_", "dev_")):
            del sys.modules[module_name]

# ---------------------------------------------------------------------------
# 最小 AstrBot mock
# ---------------------------------------------------------------------------

mock_logger = types.SimpleNamespace(
    info=lambda *a, **k: None,
    debug=lambda *a, **k: None,
    warning=lambda *a, **k: print("  [warn]", *a),
    error=lambda *a, **k: print("  [error]", *a),
)


class FakePlain:
    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return f"Plain({self.text[:40]!r})"


class FakeImage:
    def __init__(self, url: str) -> None:
        self.url = url

    @staticmethod
    def fromURL(url: str, **_: Any) -> FakeImage:
        if not url.startswith(("http://", "https://")):
            raise Exception("not a valid url")
        return FakeImage(url)

    def __repr__(self) -> str:
        return f"Image({self.url})"


class FakeResult:
    def __init__(self, chain: list[Any]) -> None:
        self.chain = chain


class FakeEvent:
    def __init__(self, message_str: str, sender_id: str = "10001") -> None:
        self.message_str = message_str
        self._sender_id = sender_id
        self.unified_msg_origin = f"mock:FriendMessage:{sender_id}"

    def get_sender_id(self) -> str:
        return self._sender_id

    def plain_result(self, text: str) -> FakeResult:
        return FakeResult([FakePlain(text)])

    def chain_result(self, chain: list[Any]) -> FakeResult:
        return FakeResult(list(chain))

    def image_result(self, url: str) -> FakeResult:
        return FakeResult([FakeImage(url)])


class FakeFilter:
    def __init__(self) -> None:
        self.commands: list[tuple[str, dict]] = []

    def command(self, name: str, **kwargs: Any):
        self.commands.append((name, kwargs))

        def decorator(func):
            return func

        return decorator


fake_filter = FakeFilter()


class FakeConfig(dict):
    def save_config(self) -> None:  # pragma: no cover
        pass


def build_modules() -> None:
    pkg = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.AstrBotConfig = FakeConfig
    api.logger = mock_logger

    event_mod = types.ModuleType("astrbot.api.event")
    event_mod.AstrMessageEvent = FakeEvent
    event_mod.filter = fake_filter

    comp_mod = types.ModuleType("astrbot.api.message_components")
    comp_mod.Image = FakeImage
    comp_mod.Plain = FakePlain

    star_mod = types.ModuleType("astrbot.api.star")

    class FakeStar:
        def __init__(self, context: Any) -> None:
            self.context = context

    star_mod.Context = object
    star_mod.Star = FakeStar
    star_mod.register = lambda *a, **k: lambda cls: cls
    star_mod.StarTools = types.SimpleNamespace()

    sys.modules.update(
        {
            "astrbot": pkg,
            "astrbot.api": api,
            "astrbot.api.event": event_mod,
            "astrbot.api.message_components": comp_mod,
            "astrbot.api.star": star_mod,
        }
    )


build_modules()

import dev_selftest as T
import main as plugin_main

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


def make_plugin(config: dict | None = None):
    data_dir = HERE / "data" / "mocktest"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    plugin = plugin_main.ApexStatsPlugin(context=None, config=FakeConfig(config or {}))
    plugin.data_dir = data_dir
    plugin.data_dir.mkdir(parents=True, exist_ok=True)
    plugin.client.cache_path = data_dir / "cache.json"
    plugin.client.api_key = "dummy-key"
    plugin._bindings = {}
    return plugin


async def drive(gen) -> list[FakeResult]:
    return [result async for result in gen]


def text_of(result: FakeResult) -> str:
    return "\n".join(part.text for part in result.chain if isinstance(part, FakePlain))


def images_of(result: FakeResult) -> list[str]:
    return [part.url for part in result.chain if isinstance(part, FakeImage)]


async def test_command_registration() -> None:
    names = [name for name, _ in fake_filter.commands]
    assert names == ["apex"], names
    alias = fake_filter.commands[0][1].get("alias")
    assert isinstance(alias, set) and "Apex" in alias, alias
    print(f"[OK] 指令注册正确：name='apex'，alias={sorted(alias)}（未叠加装饰器）")


async def test_help_and_usage() -> None:
    plugin = make_plugin()
    results = await drive(plugin.apex_handler(FakeEvent("apex help")))
    assert "Apex Legends 战绩查询" in text_of(results[0])
    results = await drive(plugin.apex_handler(FakeEvent("/apex 帮助")))
    assert "使用说明" in text_of(results[0])
    results = await drive(plugin.apex_handler(FakeEvent("/apex")))
    assert "请输入要查询的 EA ID" in text_of(results[0])
    print("[OK] help / 空参数 / 中文别名提示正确")


async def test_strip_command_variants() -> None:
    strip = plugin_main._strip_command
    assert strip("/apex shroud") == "shroud"
    assert strip("apex shroud") == "shroud"
    assert strip("/Apex shroud ps") == "shroud ps"
    assert strip("/apex") == ""
    assert strip("apex") == ""
    assert strip("/apex   shroud  ") == "shroud"
    print("[OK] 指令前缀与指令名剥离在多种触发形态下均正确")


async def test_query_with_platform() -> None:
    plugin = make_plugin({"enable_rank_image": True})
    calls: list[tuple[str, str]] = []

    async def fake_fetch(player, platform, **kwargs):
        calls.append((player, platform))
        return __import__("apex_api").parse_player_payload(T.SAMPLE), False, None

    plugin.client.fetch_player = fake_fetch
    results = await drive(plugin.apex_handler(FakeEvent("/apex shroud ps")))
    assert calls == [("shroud", "PS4")], calls
    result = results[0]
    assert images_of(result) == ["https://api.mozambiquehe.re/assets/ranks/diamond.png"], images_of(result)
    body = text_of(result)
    assert "钻石 II" in body and "恶灵" in body and "平台：PlayStation" in body
    print(f"[OK] 带平台参数查询：{calls}，消息链首段为段位图标，文本渲染正确")

    # 平台写在前面
    calls.clear()
    await drive(plugin.apex_handler(FakeEvent("/apex pc shroud")))
    assert calls == [("shroud", "PC")], calls
    print("[OK] 平台写在玩家名之前也能解析")

    # 末位参数不是平台时，整体当作玩家名（含空格）
    calls.clear()
    await drive(plugin.apex_handler(FakeEvent("/apex My Name")))
    assert calls == [("My Name", "PC")], calls
    print("[OK] 含空格的玩家名不会被误判为平台")

    # 名叫 pc 的玩家
    calls.clear()
    await drive(plugin.apex_handler(FakeEvent("/apex pc")))
    assert calls == [("pc", "PC")], calls
    print("[OK] 玩家名恰好叫 pc 时按玩家名处理")


async def test_invalid_platform_and_uid() -> None:
    plugin = make_plugin()
    calls: list[tuple[str, str]] = []

    async def fake_fetch(player, platform, **kwargs):
        calls.append((player, platform))
        return __import__("apex_api").parse_player_payload(T.SAMPLE), False, None

    plugin.client.fetch_player = fake_fetch
    # 未知平台两两组合会被当成「含空格的玩家名」，显式写法必须报错
    calls.clear()
    results = await drive(plugin.apex_handler(FakeEvent("/apex 平台:nintendo shroud")))
    assert "未知平台" in text_of(results[0]), text_of(results[0])
    assert calls == [], calls
    print("[OK] 显式指定的未知平台给出明确提示且不发起查询")

    calls.clear()
    results = await drive(plugin.apex_handler(FakeEvent("/apex shroud 平台:ns")))
    assert calls == [("shroud", "SWITCH")], calls
    print(f"[OK] 平台:xxx 显式写法可用：{calls}")

    calls.clear()
    await drive(plugin.apex_handler(FakeEvent("/apex 1000575543540")))
    assert calls == [("1000575543540", "PC")], calls
    print("[OK] 纯数字 UID 直接作为查询目标")


async def test_bind_flow() -> None:
    plugin = make_plugin()
    calls: list[tuple[str, str]] = []
    seq = {"age": None}

    async def fake_fetch(player, platform, **kwargs):
        # 第一次（绑定）是真实查询，之后按 seq["age"] 返回缓存命中
        calls.append((player, platform))
        age = seq["age"]
        return __import__("apex_api").parse_player_payload(T.SAMPLE), age is not None, age

    plugin.client.fetch_player = fake_fetch
    event = FakeEvent("/apex bind MyEAID ps")

    results = await drive(plugin.apex_handler(event))
    assert "绑定成功" in text_of(results[0]), text_of(results[0])
    assert "缓存结果" not in text_of(results[0]), "绑定不应带缓存提示"
    assert calls == [], "bind 只保存绑定，不应发起查询"
    assert plugin._bindings["10001"]["player"] == "MyEAID"
    assert plugin._bindings["10001"]["platform"] == "PS4"
    print("[OK] bind 子命令保存绑定")

    # 直接 /apex 使用绑定（命中 120 秒前的缓存）
    seq["age"] = 120.0
    results = await drive(plugin.apex_handler(FakeEvent("/apex")))
    assert calls == [("MyEAID", "PS4")], calls
    body = text_of(results[0])
    assert "缓存结果" in body and "2 分钟前" in body, body
    print(f"[OK] 未带参数时使用绑定账号查询：{calls[-1]}，并显示缓存提示")

    # 刚刚查过的缓存走另一条提示文案
    seq["age"] = 3.0
    results = await drive(plugin.apex_handler(FakeEvent("/apex")))
    assert "由于刚查过" in text_of(results[0]), text_of(results[0])
    print("[OK] 短时间内重复查询显示「刚查过」提示")

    results = await drive(plugin.apex_handler(FakeEvent("/apex unbind")))
    assert "已解除绑定" in text_of(results[0])
    assert "10001" not in plugin._bindings
    print("[OK] unbind 子命令解除绑定")

    results = await drive(plugin.apex_handler(FakeEvent("/apex unbind")))
    assert "还没有绑定" in text_of(results[0])
    print("[OK] 未绑定时给出提示")


async def test_error_and_clearcache() -> None:
    import apex_api

    plugin = make_plugin()

    async def boom(player, platform, **kwargs):
        raise apex_api.ApexApiError("NOT_FOUND")

    plugin.client.fetch_player = boom
    results = await drive(plugin.apex_handler(FakeEvent("/apex nobody")))
    assert "没有找到该玩家" in text_of(results[0]), text_of(results[0])
    print("[OK] API 错误转换为中文提示")

    async def crash(player, platform, **kwargs):
        raise RuntimeError("boom")

    plugin.client.fetch_player = crash
    results = await drive(plugin.apex_handler(FakeEvent("/apex anyone")))
    assert "未预期的错误" in text_of(results[0])
    print("[OK] 未预期异常被兜底，不会把异常抛给框架")

    plugin.client._disk = {"PC:x": {"saved_at": 0, "data": {}}}
    results = await drive(plugin.apex_handler(FakeEvent("/apex clearcache")))
    assert "已清空本地缓存" in text_of(results[0])
    print("[OK] clearcache 子命令可用")


async def test_no_api_key() -> None:
    plugin = make_plugin()
    plugin.client.api_key = ""
    results = await drive(plugin.apex_handler(FakeEvent("/apex shroud")))
    body = text_of(results[0])
    assert "还没有配置 API Key" in body and "apexlegendsapi.com/auth" in body, body
    print("[OK] 未配置 API Key 时给出可操作的提示")

    plugin = make_plugin({"enable_rank_image": False})
    plugin.client.api_key = "k"

    async def fake_fetch(player, platform, **kwargs):
        return __import__("apex_api").parse_player_payload(T.SAMPLE), False, None

    plugin.client.fetch_player = fake_fetch
    results = await drive(plugin.apex_handler(FakeEvent("/apex shroud")))
    assert images_of(results[0]) == [], images_of(results[0])
    assert len(results[0].chain) == 1
    print("[OK] 关闭段位图标后只发送文本")


async def test_terminate() -> None:
    plugin = make_plugin()
    await plugin.terminate()  # 不应抛异常
    print("[OK] terminate 生命周期安全")


async def main() -> int:
    await test_command_registration()
    await test_help_and_usage()
    await test_strip_command_variants()
    await test_query_with_platform()
    await test_invalid_platform_and_uid()
    await test_bind_flow()
    await test_error_and_clearcache()
    await test_no_api_key()
    await test_terminate()
    print("\n✅ main.py 全部指令链路测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
