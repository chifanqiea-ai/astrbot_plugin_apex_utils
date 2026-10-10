"""插件离线自测脚本（不依赖 AstrBot 框架）。

用法：
    python dev_selftest.py            # 仅离线自测（解析 / 渲染 / 参数解析）
    python dev_selftest.py <API_KEY>  # 额外做一次真实 API 联调
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import apex_api
import apex_constants as C

SAMPLE = {
    "global": {
        "name": "TestPlayer",
        "tag": "TestTag",
        "uid": "1234567890123",
        "avatar": "https://example.com/avatar.png",
        "platform": "PC",
        "level": 500,
        "levelPrestige": 2,
        "kills": 12345,
        "damage": 4567890,
        "wins": 620,
        "matches": 8765,
        "bans": {"isActive": False, "remainingSeconds": 0},
        "rank": {
            "rankScore": {"rankedScore": 12345, "ladderScore": 12800.5},
            "rankName": "Diamond",
            "rankDiv": 2,
            "ladderPosPlatform": 15234,
            "rankImg": "https://api.mozambiquehe.re/assets/ranks/diamond.png",
            "rankedSeasonLevel": 120,
        },
    },
    "legends": {
        # v5 真实形态：legend 名作为键，数据卡是展开的字典
        "selected": {
            "Wraith": {
                "kills": 4321,
                "damage": 1234567,
                "season_kills": 321,
                "level": 500,
                "ImgAssets": {"icon": "https://example.com/wraith.png"},
            }
        },
        # 旧版数组形态，用于验证兼容性
        "all": [
            {
                "legendName": "Wraith",
                "legendNameEn": "Wraith",
                "ImgAssets": {"icon": "https://example.com/wraith.png"},
                "data": [
                    {"key": "kills", "value": 4321, "name": "Kills"},
                    {"key": "damage", "value": 1234567, "name": "Damage"},
                    {"key": "season_kills", "value": 321, "name": "Season Kills"},
                    {"key": "level", "value": 500},
                ],
            },
            {
                "legendName": "Lifeline",
                "ImgAssets": {"icon": "https://example.com/lifeline.png"},
                "data": [
                    {"key": "kills", "value": 958, "name": "Kills"},
                    {"key": "damage", "value": 254506, "name": "Damage"},
                ],
            },
            {
                "legendName": "Octane",
                "ImgAssets": {"icon": "https://example.com/octane.png"},
                "data": [
                    {"key": "kills", "value": 2130, "name": "Kills"},
                    {"key": "damage", "value": 654321, "name": "Damage"},
                ],
            },
        ],
    },
    "total": {
        "kills": {"name": "Kills", "value": 12345},
        "damage": {"name": "Damage", "value": 4567890},
        "wins": {"name": "Wins", "value": 620},
        "games_played": {"name": "Games played", "value": 8765},
        "headshots": {"name": "Headshots", "value": 1234},
        "care_package_kills": {"name": "Care package kills", "value": 88},
        "kd": {"name": "KD", "value": -1},
        "season_kills": {"name": "Season kills", "value": 321},
        "level": {"name": "Level", "value": 500},
    },
    "realtime": {"lobbyState": "open", "isOnline": 1},
}


def test_parse() -> None:
    data = apex_api.parse_player_payload(SAMPLE)
    overall = data["overall"]
    assert overall["name"] == "TestPlayer", overall
    # global 里没有 kills/matches 时，应回退到 total.*.value
    assert overall["kills"] == 12345, overall["kills"]
    assert overall["damage"] == 4567890, overall["damage"]
    assert overall["matches"] == 8765, overall["matches"]
    assert overall["rp"] == 12345, overall["rp"]
    assert overall["rank_name"] == "Diamond"
    assert overall["rank_div"] == 2
    assert data["legend"]["name"] == "Wraith"
    assert ("kills", "4,321") in data["legend"]["trackers"], data["legend"]["trackers"]
    # level 数据卡应被过滤
    assert all(key != "level" for key, _ in data["legend"]["trackers"])
    # 常用传奇按击杀数降序
    top = data["top_legends"]
    assert [entry["name"] for entry in top] == ["Wraith", "Octane", "Lifeline"], top
    # total 归一化后是展示值
    assert data["trackers"]["kills"] == "12,345"
    assert data["trackers"]["kd"] == "-1"
    print("[OK] parse_player_payload 解析正确（含 v5 字典形态 / 旧版数组形态 / total 对象形态）")


def test_uid_parse() -> None:
    cases = [
        ({"uid": "1000575543540"}, "1000575543540"),
        ({"result": "1000575543540"}, "1000575543540"),
        ({"uid": {"uid": "123"}}, "123"),
        ([{"uid": "123", "name": "a"}], "123"),
        ({"data": {"uid": "456"}}, "456"),
        ({"Error": "nope"}, ""),
        ("", ""),
    ]
    for payload, expected in cases:
        got = apex_api._parse_uid(payload)
        assert got == expected, f"{payload} -> {got!r} != {expected!r}"
    print("[OK] /nametouid 响应兼容解析正确（dict / list / result / data）")


def test_render() -> None:
    data = apex_api.parse_player_payload(SAMPLE)
    text = apex_api.format_player_text(
        data,
        platform="PC",
        max_trackers=8,
        preferred_trackers=C.PREFERRED_TRACKERS,
        ignored_trackers=C.IGNORED_TRACKERS,
    )
    print("\n===== 渲染预览 =====\n" + text + "\n====================\n")
    assert "TestPlayer" in text
    assert "钻石 II" in text, text
    assert "12,345 RP" in text, text
    assert "Lv.500" in text
    assert "威望 2" in text
    assert "恶灵" in text, "传奇名未翻译"
    assert "击杀：4,321" in text, "传奇数据卡未翻译"
    # KD 为 -1 时不应展示
    assert "KD：-1" not in text, "KD=-1 应被跳过"
    # 常用传奇段落
    assert "── 常用传奇 ──" in text, text
    assert "生命线" in text, "常用传奇未翻译"
    print("[OK] format_player_text 渲染正确（段位/传奇/数据卡均已中文化，KD=-1 已跳过）")


def test_platform() -> None:
    assert apex_api.normalize_platform("pc") == "PC"
    assert apex_api.normalize_platform("PS5") == "PS4"
    assert apex_api.normalize_platform("xbox") == "X1"
    assert apex_api.normalize_platform("switch") == "SWITCH"
    assert apex_api.normalize_platform("PC") == "PC"
    assert apex_api.normalize_platform("nope", default="") == ""
    assert apex_api.platform_label("X1") == "Xbox"
    print("[OK] 平台解析正确")


def test_helpers() -> None:
    assert apex_api.to_int("1,234") == 1234
    assert apex_api.to_int(None) == 0
    assert apex_api.to_int(True) == 0
    assert apex_api.perfect_score({"rankedScore": 999, "ladderScore": 1.5}) == 999
    assert apex_api.perfect_score(777) == 777
    assert apex_api.format_number(1234567) == "1,234,567"
    assert C.translate_rank("Master") == "大师"
    assert C.translate_rank("Unknown") == "Unknown"
    assert C.translate_tracker("season_kills") == "赛季击杀"
    assert C.translate_tracker("some_new_tracker") == "Some New Tracker"
    print("[OK] 数值/翻译工具正确")


def test_errors() -> None:
    err = apex_api.ApexApiError("NOT_FOUND")
    assert "没有找到该玩家" in err.user_message
    err2 = apex_api.ApexApiError("API_ERROR", "boom")
    assert "boom" in err2.user_message
    try:
        apex_api.parse_player_payload({})
    except apex_api.ApexApiError as exc:
        assert exc.code == "EMPTY_RESULT"
    else:  # pragma: no cover
        raise AssertionError("空响应未抛出 EMPTY_RESULT")
    print("[OK] 错误文案映射正确")


async def test_live(api_key: str) -> None:
    from pathlib import Path as _Path

    client = apex_api.ApexApiClient(
        api_key=api_key,
        cache_path=_Path(__file__).resolve().parent / "data" / "selftest_cache.json",
        logger=None,
    )
    for player in ("Miaoyww", "shroud"):
        try:
            data, cached = await client.fetch_player(player, "PC")
        except apex_api.ApexApiError as exc:
            print(f"[LIVE] {player}: 查询失败 -> {exc.code} | {exc.user_message}")
            continue
        overall = data["overall"]
        print(
            f"[LIVE] {player}: name={overall['name']} uid={overall['uid']} "
            f"level={overall['level']} rank={overall['rank_name']} div={overall['rank_div']} "
            f"rp={overall['rp']} kills={overall['kills']} cached={cached}"
        )
        print(f"[LIVE] rankImg={overall['rank_img']}")
        text = apex_api.format_player_text(data, "PC", 8, C.PREFERRED_TRACKERS, C.IGNORED_TRACKERS)
        print(text[:800])


def main() -> int:
    test_helpers()
    test_platform()
    test_errors()
    test_uid_parse()
    test_parse()
    test_render()
    print("\n✅ 全部离线自测通过")
    if len(sys.argv) > 1 and sys.argv[1].strip():
        print(f"\n>>> 开始真实 API 联调（key 长度 {len(sys.argv[1].strip())}）")
        asyncio.run(test_live(sys.argv[1].strip()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
