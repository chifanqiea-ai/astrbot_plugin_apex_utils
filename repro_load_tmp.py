"""临时脚本：用真实 AstrBot 的类，模拟 star_manager 加载插件的过程。测试完即删。"""
import sys

sys.path.insert(0, r"G:\AstrBot\venv\Lib\site-packages")
sys.path.insert(0, r"G:\AstrBot")  # 让插件目录下的 data/ 路径真实存在

# 把插件目录作为包插入 sys.path（模拟 AstrBot 的插件目录）
sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace")

from astrbot.core.config import AstrBotConfig  # noqa: E402
from astrbot.core.star.context import Context  # noqa: E402
from astrbot.core.star.star import star_map  # noqa: E402

# 1) 包形式导入插件模块（AstrBot 用 __import__(path, fromlist=['main'])）
import astrbot_plugin_apex_stats.main as plugin_main  # noqa: E402

print("== 导入成功 ==")
print("star_map 条目:", {k: v.star_cls_type for k, v in star_map.items()})
meta = star_map.get("astrbot_plugin_apex_stats.main")
print("元数据 name:", getattr(meta, "name", None), "| author:", getattr(meta, "author", None))

# 2) 构造真实 AstrBotConfig（按 star_manager 的做法：schema + 配置文件路径）
plugin_config = AstrBotConfig(
    config_path=r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\astrbot_plugin_apex_stats\_tmp_plugin_config.json",
    schema=None,
)
print("AstrBotConfig 类型:", type(plugin_config))

# 3) 最小 Context（插件 __init__ 只存引用，不调用方法）
context = object.__new__(Context)
print("== 开始实例化插件 ==")
plugin = plugin_main.ApexStatsPlugin(context=context, config=plugin_config)
print("== 实例化成功 ==")
print("data_dir:", plugin.data_dir)
print("has_api_key:", plugin.client.has_api_key)
