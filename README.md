# Apex 战绩查询（astrbot_plugin_apex_stats）

在聊天中用指令按 **EA ID** 查询 Apex Legends 玩家战绩：等级、段位（含段位图标）、生涯总击杀/伤害/胜场、数据卡、当前传奇与常用传奇。

```
你：/apex shroud
Bot：【shroud】Apex Legends 战绩
     平台：PC (EA/Origin)
     ━━━━━━━━━━━━━━
     等级：Lv.500（威望 2）
     段位：钻石 II｜12,345 RP
     ...
```

## ✨ 功能

| 功能 | 说明 |
| --- | --- |
| 按 EA ID 查询 | `/apex <EA ID>`，PC 平台填 EA / Origin 账号名（**不是 Steam 昵称**） |
| 多平台 | 默认 PC，可用 `ps` / `xbox` / `switch` 覆盖 |
| UID 直接查询 | 输入纯数字 UID 时自动改用 UID 查询 |
| 改名免疫 | 首次查到的 UID 会被记住，之后玩家改名也能查到 |
| 段位图标 | 附带段位徽章图片（可关闭） |
| 结果缓存 | 默认 5 分钟，避免触发 API 限流；数据源故障时自动回退到上次结果 |
| 账号绑定 | `/apex bind <EA ID>` 后，直接发 `/apex` 查自己 |
| 中文化 | 段位、传奇、数据卡名称全部映射为中文，未知名称原样展示 |

## 📦 安装

1. 把整个 `astrbot_plugin_apex_stats` 文件夹放入 AstrBot 的 `data/plugins/` 目录
   （或在 WebUI「插件管理」中上传 `astrbot_plugin_apex_stats.zip`）。
2. 重载插件，在 WebUI → 插件管理 → **Apex 战绩查询** → 配置中填写 `api_key`。
3. 发送 `/apex help` 验证。

依赖：`httpx`（AstrBot 自带）。若环境缺失，插件会自动退化到 `aiohttp`，再退化到标准库 `urllib`，**无需额外安装**。

## 🔑 获取 API Key（必填）

1. 打开 <https://apexlegendsapi.com/auth> 注册，获得免费 API Key。
2. 按门户提示**绑定 Discord 账号**（未验证的 Key 容易被限流或不可用）。
3. 把 Key 填入插件配置 `api_key`。

> 同一把 Key 也可用于 `https://api.mozambiquehe.re`（默认）与 `https://api.apexlegendsstatus.com`，两者是同一套接口。

## 🎮 指令

| 指令 | 作用 |
| --- | --- |
| `/apex <EA ID> [平台]` | 查询指定玩家，例如 `/apex shroud`、`/apex shroud ps`、`/apex pc shroud` |
| `/apex` | 查询自己已绑定的 EA ID |
| `/apex bind <EA ID> [平台]` | 绑定自己的 EA ID |
| `/apex unbind` | 解除绑定 |
| `/apex clearcache` | 清空本地查询缓存 |
| `/apex help` | 显示帮助 |

别名：`/Apex`、`/APEX`、`/查询战绩`、`/查战绩`。

平台关键字：`pc`（= `ea` / `origin` / `steam`）、`ps`（= `ps4` / `ps5` / `playstation`）、`xbox`（= `x1` / `xb`）、`switch`（= `ns`）。

参数顺序任意，也可用显式写法 `平台:ps`。**含空格的玩家名**请写在最后或使用 bind：
`/apex My Name` 会把 `My Name` 当作玩家名。

## ⚙️ 配置项（`_conf_schema.json`）

| 键 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `api_key` | string（密文） | 空 | **必填**，Mozambique Heirloom API Key |
| `api_base` | string | `https://api.mozambiquehe.re` | 数据源地址，可换成 `https://api.apexlegendsstatus.com` |
| `default_platform` | string | `PC` | 未在指令中指定平台时使用，可选 `PC`/`PS4`/`X1`/`SWITCH` |
| `enable_rank_image` | bool | `true` | 是否附带段位徽章图片 |
| `max_trackers` | int | `8` | 战绩文本里展示的数据卡条数 |
| `cache_ttl` | int | `300` | 缓存有效期（秒），`0` 表示不缓存 |
| `request_timeout` | int | `15` | 单次请求超时（秒） |
| `show_cache_hint` | bool | `true` | 命中缓存时在末尾追加提示 |

## 🗂 目录结构

```
astrbot_plugin_apex_stats/
├── main.py                 # 插件入口：指令注册、参数解析、绑定、消息组装
├── apex_api.py             # API 客户端：请求、缓存、限流、解析、错误映射
├── apex_constants.py       # 段位/传奇/数据卡中英映射与常量
├── _conf_schema.json       # 插件配置 Schema（WebUI 可视化配置）
├── metadata.yaml           # 插件元数据
├── requirements.txt        # 依赖声明（可选安装）
├── pyproject.toml          # ruff 格式化 / lint 配置
├── PUBLISHING.md           # 发布手册
├── README.md
└── dev_*.py                # 开发自测脚本（可删除，不影响运行）
```

## 🧪 开发自测

三个脚本都不依赖 AstrBot 运行环境，用任意 Python 3.10+ 直接运行：

```bash
python dev_selftest.py          # 解析 / 渲染 / 翻译 单元自测（含渲染预览）
python dev_test_client.py       # 请求参数、缓存、UID 优先、错误映射、限流
python dev_test_client.py --live   # 追加一次真实网络连通性探测
python dev_test_plugin.py       # 用最小 AstrBot mock 驱动 main.py 指令链路
```

## ❓ 常见问题

**提示「没有找到该玩家」**
PC 平台必须填 **EA / Origin 账号名**（Apex 内显示的名字），Steam 昵称无效。若玩家在 Steam 上玩，请填其绑定的 EA 账号名；也可直接填 UID。

**段位显示「未定级」**
该玩家本赛季未打过排位，或数据源尚未收录。

**图片发不出来**
部分平台适配器不支持图片消息，可在配置中关闭 `enable_rank_image`，文本战绩不受影响。

**查询很慢或提示限流**
免费 Key 有速率限制，插件已内置 1 次/秒节流、结果缓存与 `X-Current-Rate` 自适应。可在配置中调大 `cache_ttl`。

**`total.kd` 显示异常**
官方在该数据不足时返回 `-1`，插件会自动隐藏该项而不是显示 `-1`。

## ⚠️ 说明与免责

- 数据来自第三方非官方接口 [Mozambique Heirloom API](https://apexlegendsapi.com/)（apexlegendsstatus.com），**与 EA / Respawn 无关**，可能随时变更或不可用。
- 请遵守数据源的使用条款，不要高频轮询。
- 本项目仅用于学习与娱乐。

## 📄 许可

[MIT](LICENSE)

---

## 🚀 发布与贡献

- 发布到 AstrBot 插件市场的完整流程见 [PUBLISHING.md](PUBLISHING.md)
- 发布前自检：`python dev_check_release.py`
- 提交代码前请执行 `ruff format . && ruff check .`

> 发布前请替换这些占位符：`metadata.yaml` 的 `author` / `repo` / `social_link`，以及 `LICENSE` 中的版权人（当前为 `your-github-name`）。

