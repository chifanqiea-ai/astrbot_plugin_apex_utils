"""临时脚本：用真实 API Key 联网查询战绩（测试完即删）。"""

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import apex_api


async def main() -> int:
    client = apex_api.ApexApiClient(
        api_key="23a3b7f858a8ae6b21c0d852e007cc76",
        base_url="https://api.mozambiquehe.re",
        timeout=20,
        cache_ttl=0,  # 测试时不用缓存
        cache_path=HERE / "data" / "live_test_cache_tmp.json",
        logger=None,
    )
    # 依次尝试几个知名玩家名，直到成功
    candidates = ["shroud", "ImperialHal", "aceu", "Timmy"]
    for name in candidates:
        print(f"\n===== 查询 {name}（PC 平台）=====")
        try:
            data, cached, age = await client.fetch_player(name, "PC")
        except apex_api.ApexApiError as exc:
            print(f"查询失败：错误码 {exc.code}")
            print(f"提示文案：{exc.user_message}")
            continue
        overall = data.get("overall") or {}
        print(f"原始名称：{overall.get('name')} | UID：{overall.get('uid')}")
        print(f"等级：{overall.get('level')} | 威望：{overall.get('prestige')}")
        print(f"段位：{overall.get('rank_name')} {overall.get('rank_div')} | RP：{overall.get('rp')}")
        print(f"击杀：{overall.get('kills')} | 伤害：{overall.get('damage')} | 胜场：{overall.get('wins')}")
        print("\n-------- 渲染后的战绩文本 --------")
        text = apex_api.format_player_text(data, "PC")
        print(text)
        print("\n===== 真实查询成功 ✅ =====")
        return 0
    print("\n===== 所有候选玩家都查询失败 ❌ =====")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
