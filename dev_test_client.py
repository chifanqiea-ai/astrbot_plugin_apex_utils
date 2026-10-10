"""联调与错误处理测试：真实网络错误映射 + 假响应驱动的完整链路（无需真实 API Key）。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import apex_api

CACHE = HERE / "data" / "devtest_cache.json"


class FakeClient(apex_api.ApexApiClient):
    """用假响应替换网络层，验证请求参数、错误映射与缓存链路。"""

    def __init__(self, *args, response=None, error_code=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.response = response
        self.error_code = error_code
        self.calls: list[tuple[str, dict]] = []

    async def _request(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if self.error_code:
            raise apex_api.ApexApiError(self.error_code)
        if endpoint == "nametouid":
            return {"uid": "1000575543540"}
        return self.response


def make_client(**kwargs) -> FakeClient:
    import dev_selftest as T

    return FakeClient(
        api_key="dummy-key",
        cache_path=CACHE,
        logger=None,
        response=T.SAMPLE,
        **kwargs,
    )


async def test_request_params() -> None:
    client = make_client()
    data, cached, age = await client.fetch_player("HeyImLifeline", "pc")
    assert cached is False and age is None
    endpoint, params = client.calls[0]
    assert endpoint == "bridge", client.calls
    assert params["player"] == "HeyImLifeline", params
    assert params["platform"] == "PC", params
    assert params["version"] == 5 and params["merge"] == 1, params
    assert client.api_key == "dummy-key"  # auth 由 _request 统一注入
    print(f"[OK] 首次查询请求参数正确：{params}")

    # 第二次应命中缓存，不再发起请求
    data2, cached2, age2 = await client.fetch_player("HeyImLifeline", "PC")
    assert cached2 is True and age2 is not None and len(client.calls) == 1
    print(f"[OK] 缓存命中生效（未重复请求，缓存年龄 {age2:.1f}s）")


async def test_uid_first() -> None:
    """已知名字→UID 后，应优先使用 uid 参数查询。"""
    client = make_client()
    await client.fetch_player("HeyImLifeline", "PC")  # 建立名字→UID 映射
    assert client._uid_map.get("PC:heyimlifeline") == "1234567890123", client._uid_map
    client.calls.clear()
    client._memory.clear()
    client._disk.clear()  # 绕过缓存，验证「已知 UID 优先」这条分支
    await client.fetch_player("HeyImLifeline", "PC")
    endpoint, params = client.calls[0]
    assert "uid" in params and params["uid"] == "1234567890123", params
    assert "player" not in params, params
    print(f"[OK] 已知 UID 时优先按 uid 查询：{params}")


async def test_uid_input() -> None:
    """用户直接输入纯数字 UID 时，应直接走 uid 参数。"""
    client = make_client()
    await client.fetch_player("1000575543540", "PC")
    endpoint, params = client.calls[0]
    assert params.get("uid") == "1000575543540", params
    print(f"[OK] 数字输入按 UID 查询：{params}")


async def test_not_found_fallback() -> None:
    """名字查询失败时应尝试 /nametouid 再查一次，且返回正确错误。"""

    class NotFoundThenOk(FakeClient):
        async def _request(self, endpoint, params):
            self.calls.append((endpoint, dict(params)))
            if endpoint == "nametouid":
                return {"uid": "1000575543540"}
            if "player" in params:
                raise apex_api.ApexApiError("NOT_FOUND")
            import dev_selftest as T

            return T.SAMPLE

    client = NotFoundThenOk(api_key="dummy-key", cache_path=CACHE, logger=None)
    data, _cached, _age = await client.fetch_player("SomeRenamedPlayer", "PC")
    endpoints = [call[0] for call in client.calls]
    assert endpoints == ["bridge", "nametouid", "bridge"], endpoints
    assert client.calls[-1][1].get("uid") == "1000575543540"
    assert data["overall"]["name"] == "TestPlayer"
    print(f"[OK] 名字失败后自动解析 UID 重试成功：{endpoints}")


async def test_error_mapping() -> None:
    for code in ("NO_API_KEY", "NOT_FOUND", "RATE_LIMITED", "INVALID_API_KEY", "TIMEOUT"):
        client = make_client(error_code=code)
        if code == "NO_API_KEY":
            client.api_key = ""
        try:
            await client.fetch_player("Someone", "PC")
        except apex_api.ApexApiError as exc:
            assert exc.code == code, (exc.code, code)
            assert exc.user_message.strip(), "错误文案为空"
        else:
            raise AssertionError(f"{code} 未抛出异常")
    print("[OK] 各类错误均映射为中文提示文案")


async def test_stale_cache_fallback() -> None:
    """API 不可用时应回退到过期缓存。"""
    client = make_client(cache_ttl=0)
    await client.fetch_player("HeyImLifeline", "PC")
    client._memory.clear()
    client.cache_ttl = 0

    class Failing(FakeClient):
        async def _request(self, endpoint, params):
            self.calls.append((endpoint, dict(params)))
            raise apex_api.ApexApiError("NETWORK", "connection reset")

    failing = Failing(api_key="dummy-key", cache_path=CACHE, logger=None)
    failing._disk = client._disk
    data, cached, age = await failing.fetch_player("HeyImLifeline", "PC")
    assert cached is True and data["overall"]["name"] == "TestPlayer"
    print("[OK] 数据源不可用时回退到过期缓存")


async def test_rate_limit_headers() -> None:
    client = make_client()
    client.note_response({"X-Current-Rate": "1;5"})
    assert abs(client._min_interval - 1.05) < 0.001, client._min_interval
    client.note_response({"X-Current-Rate": "1;1"})
    assert abs(client._min_interval - 1.05) < 0.001, client._min_interval
    client.note_response({})
    print(f"[OK] 限流自适应解析正确（当前最小间隔 {client._min_interval:.2f}s）")


async def test_live() -> None:
    """真实网络：验证 DNS/TLS/可达性以及错误码映射（用无效 key 探测）。"""
    client = apex_api.ApexApiClient(
        api_key="invalid_key_connectivity_probe",
        cache_path=HERE / "data" / "probe_cache.json",
        logger=None,
        timeout=20,
    )
    try:
        await client.fetch_player("shroud", "PC")
    except apex_api.ApexApiError as exc:
        print(f"[LIVE] 真实请求返回错误码：{exc.code} → {exc.user_message[:120]}")
    else:
        print("[LIVE] 意外成功（说明 key 有效或服务端放行）")


async def main() -> int:
    # 每次运行从干净缓存开始，保证「首次查询」的断言稳定
    if CACHE.exists():
        CACHE.unlink()
    await test_request_params()
    await test_uid_first()
    await test_uid_input()
    await test_not_found_fallback()
    await test_error_mapping()
    await test_stale_cache_fallback()
    await test_rate_limit_headers()
    if "--live" in sys.argv:
        await test_live()
    print("\n✅ 全部链路测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
