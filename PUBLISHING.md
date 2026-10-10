# 发布手册 · astrbot_plugin_apex_stats

从零把 Apex 战绩查询插件发布到 AstrBot 插件市场的完整流程。

> 本手册针对当前仓库（`astrbot_plugin_apex_stats` v1.0.0）。
> 文中所有需要你替换的占位符统一为 **`your-github-name`**，执行前请全文搜索替换。

---

## 目录

- [0. 发布前必读：三条硬规则](#0-发布前必读三条硬规则)
- [1. 第一步：确定插件身份](#1-第一步确定插件身份)
- [2. 第二步：核对元数据与发布文件](#2-第二步核对元数据与发布文件)
- [3. 第三步：本地发布前自检](#3-第三步本地发布前自检)
- [4. 第四步：推送到 GitHub](#4-第四步推送到-github)
- [5. 第五步：提交到插件市场](#5-第五步提交到插件市场)
- [6. 第六步：发布后的维护](#6-第六步发布后的维护)
- [7. 发布检查清单](#7-发布检查清单)
- [8. 常见问题与排错](#8-常见问题与排错)
- [9. 本手册的信息来源与未确认项](#9-本手册的信息来源与未确认项)

---

## 0. 发布前必读：三条硬规则

| 规则 | 说明 | 后果 |
| --- | --- | --- |
| **插件身份 = `author` + `name`** | 全局唯一，等同于 `metadata.author + "/" + metadata.name` | 身份冲突会导致安装失败或与别人的插件互相覆盖 |
| **zip 不得超过 16 MB** | 官方 CI/CD 会直接拒绝超限的发布请求 | 打包失败，需要精简资源后重来 |
| **`repo` 必须是 GitHub 仓库地址** | 只接受 `https://github.com/<owner>/<repo>` 形式 | 市场无法解析安装源，审核不通过 |

插件市场通过 `repo` 拉取代码，**不接收手工上传的 zip 作为市场安装源**；`zip` 只用于本地/离线安装与自测。

---

## 1. 第一步：确定插件身份

### 1.1 插件名（`metadata.yaml` 的 `name`）

官方命名要求：

- 推荐以 `astrbot_plugin_` 开头
- 不能包含空格
- 全部小写
- 尽量简短

当前值：`astrbot_plugin_apex_stats` ✅ 符合要求。

> ⚠️ 插件名一旦发布就**不要再改**：市场用 `author/name` 作为唯一标识，改名等同于发布一个全新插件，老用户收不到更新。

### 1.2 作者名（`metadata.yaml` 的 `author`）

`author` 会成为插件标识的一部分。建议直接使用 GitHub 用户名，保证长期稳定。

```yaml
author: your-github-name      # 改成你的 GitHub 用户名
```

### 1.3 仓库地址（`metadata.yaml` 的 `repo`）

```yaml
repo: https://github.com/your-github-name/astrbot_plugin_apex_stats
```

允许的三种写法（其他形式都会被判为非法）：

```
https://github.com/<owner>/<repo>
https://github.com/<owner>/<repo>.git
https://github.com/<owner>/<repo>/tree/<branch>
```

**不允许**：`http://`、SSH 地址、非 GitHub 域名、GitHub Enterprise、指向具体文件 / Release / PR / 子目录的地址。

### 1.4 版本号（`metadata.yaml` 的 `version`）

遵循语义化版本（SemVer），**不要加 `v` 前缀**：

```yaml
version: 1.0.0
```

| 变更类型 | 版本递增 | 例子 |
| --- | --- | --- |
| 修复 bug、文案调整 | PATCH | `1.0.0` → `1.0.1` |
| 新增指令 / 配置项（向后兼容） | MINOR | `1.0.0` → `1.1.0` |
| 破坏性变更（改指令名、改配置键） | MAJOR | `1.0.0` → `2.0.0` |

---

## 2. 第二步：核对元数据与发布文件

### 2.1 `metadata.yaml` 字段总表

| 字段 | 必填 | 当前值 | 说明 |
| --- | --- | --- | --- |
| `name` | ✅ | `astrbot_plugin_apex_stats` | 插件标识符，全小写唯一 |
| `display_name` | 可选 | `Apex 战绩查询` | 插件市场展示名 |
| `short_desc` | 可选 | 一句话介绍 | 市场卡片短描述，缺省时回退 `desc` |
| `desc` | ✅ | 多行说明 | 详细描述，支持 Markdown |
| `version` | ✅ | `1.0.0` | 语义化版本 |
| `author` | ✅ | `your-github-name` | **发布前必须替换** |
| `repo` | ✅ | `https://github.com/...` | **发布前必须替换** |
| `astrbot_version` | 可选 | `>=4.0.0` | 版本约束（PEP 440），**不要加 `v` 前缀** |
| `support_platforms` | 可选 | 18 个适配器 | 取值必须是官方适配器 key |
| `social_link` | 可选 | 你的主页 | 作者 / 项目链接 |
| `tags` | 可选 | 游戏、查询… | 市场分类与搜索 |
| `logo` | 可选 | — | 也可直接在插件目录放 `logo.png` |

`support_platforms` 只允许以下取值（写错不会报错，但 WebUI 不会展示）：

```
aiocqhttp  qq_official  qq_official_webhook  telegram  wecom  wecom_ai_bot
lark  dingtalk  discord  slack  kook  vocechat  weixin_official_account
weixin_oc  satori  misskey  line  matrix  mattermost
```

### 2.2 插件 Logo（可选，建议加）

在插件目录放置 `logo.png`：

- 长宽比 1:1，推荐 256×256
- 体积控制在几十 KB 以内（占用 16 MB 配额）

### 2.3 仓库文件清单

**会随插件分发给用户的运行文件**（必须保留）：

```
astrbot_plugin_apex_stats/
├── main.py               # 插件入口
├── apex_api.py           # API 客户端
├── apex_constants.py     # 中英映射常量
├── _conf_schema.json     # 插件配置 Schema
├── metadata.yaml         # 插件元数据（市场解析依赖）
├── requirements.txt      # 依赖声明
├── README.md             # 用户文档
├── LICENSE               # 开源许可
└── docs/preview.png      # 效果预览图（README 引用）
```

**仓库里建议保留、但用户不需要的文件**（体积很小，可留）：

```
├── pyproject.toml        # ruff 格式化/lint 配置（官方要求提交前用 ruff）
├── .gitignore
└── dev_*.py              # 开发自测脚本，见 2.4
```

### 2.4 关于 `dev_*.py` 自测脚本

当前仓库根目录有 4 个开发脚本：

| 文件 | 作用 | 是否随发布 |
| --- | --- | --- |
| `dev_selftest.py` | 解析 / 渲染 / 翻译单元自测 | 建议保留，便于贡献者回归 |
| `dev_test_client.py` | 请求参数、缓存、错误映射、限流 | 建议保留 |
| `dev_test_plugin.py` | 用 mock AstrBot 驱动指令链路 | 建议保留 |
| `dev_check_release.py` | **发布前自检**（元数据、结构、体积） | 建议保留 |
| `dev_make_preview.py` | 生成 README 预览图 | 保留（改渲染样式后需重跑） |

它们不会被 AstrBot 加载，也不影响运行。如果你希望发布包绝对干净，可以在建发布分支时删除，代价是后续维护失去回归测试。

### 2.5 敏感信息检查（重要）

发布前确认仓库里**没有任何真实 API Key**：

```bash
# 在仓库根目录执行，确认无输出
git grep -nE "auth=[A-Za-z0-9]{20,}" -- . || echo "未发现硬编码 Key"
```

本插件的 `api_key` 走 `_conf_schema.json` 配置注入，代码中不含默认 Key ✅。

---

## 3. 第三步：本地发布前自检

### 3.1 运行发布自检脚本

```bash
python dev_check_release.py
```

它会校验：`metadata.yaml` 必填字段与格式、`repo` 地址合法性、`support_platforms` 合法性、`_conf_schema.json` 结构、必需文件是否存在、体积是否超 16 MB、是否残留 `__pycache__` 等脏文件、占位符是否忘记替换。

期望输出（替换占位符后应无任何警告）：

```
插件名：astrbot_plugin_apex_stats｜版本：1.0.0｜作者：your-github-name
体积：281 KB（上限 16 MB）
支持平台：18 个
  [警告] repo / author 仍是占位符 your-github-name，发布前必须替换

✅ 发布前自检通过（1 条提醒）
```

### 3.2 运行回归测试

```bash
python dev_selftest.py        # 离线单元自测
python dev_test_client.py     # 请求/缓存/错误映射
python dev_test_plugin.py     # 指令链路（mock AstrBot）
```

> 官方开发原则要求「功能需经过测试」。三个脚本都不依赖 AstrBot 运行环境，任何 Python 3.12+ 环境都能跑。

### 3.3 代码格式化与检查（官方明确要求）

官方开发原则原文：**「在进行提交前，请使用 ruff 工具格式化您的代码。」**

```bash
pip install ruff
ruff format .        # 格式化
ruff check .         # 静态检查
ruff check --fix .   # 自动修复可修复项
```

当前仓库已配置 `pyproject.toml`（`line-length = 120`，`target-version = "py312"`），直接运行即可：

```
All checks passed!
9 files already formatted
```

### 3.4 生成安装包（用于本地安装与自测）

```powershell
# Windows PowerShell
Compress-Archive -Path .\astrbot_plugin_apex_stats -DestinationPath .\astrbot_plugin_apex_stats.zip
```

```bash
# macOS / Linux
zip -r astrbot_plugin_apex_stats.zip astrbot_plugin_apex_stats -x "*/__pycache__/*" "*/.git/*"
```

包内**根目录必须是插件目录本身**（即压缩后第一层是 `astrbot_plugin_apex_stats/`），不要嵌套多余层级。

### 3.5 在真实 AstrBot 上验证（强烈建议）

发布前至少走一遍真机流程：

1. 把插件目录放进 `AstrBot/data/plugins/`（或 WebUI 上传 zip）
2. WebUI → 插件管理 → 重载插件，确认日志出现 `[Apex] 插件已加载`
3. 在插件配置里填入真实 API Key
4. 依次验证：`/apex help` → `/apex <真实EA ID>` → `/apex bind <EA ID>` → `/apex` → `/apex unbind`
5. 检查：段位图标能否正常显示、缓存提示是否出现、错误提示是否可读

---

## 4. 第四步：推送到 GitHub

### 4.1 创建 GitHub 仓库

1. 打开 <https://github.com/new>
2. **Repository name** 填 `astrbot_plugin_apex_stats`（与 `metadata.name` 保持一致，便于识别）
3. 可见性选 **Public**（插件市场需要能公开拉取）
4. **不要**勾选 "Add a README file" / ".gitignore" / "license"（本地已有，避免冲突）
5. 创建仓库

### 4.2 初始化并提交本地仓库

在插件目录**的上一级**（即工作区根目录）确认插件目录已是独立仓库根：

```bash
cd astrbot_plugin_apex_stats

git init
git branch -M main
git config user.name  "your-github-name"
git config user.email "you@example.com"

# 确认将被提交的文件（不应出现 __pycache__ / data/）
git add .
git status

git commit -m "feat: Apex 战绩查询插件 v1.0.0"
```

> `.gitignore` 已排除 `data/`、`__pycache__/`、`*.zip`、`.env` 等，`git status` 里出现这些文件说明 `.gitignore` 未生效。

### 4.3 关联远程仓库并推送

```bash
git remote add origin https://github.com/your-github-name/astrbot_plugin_apex_stats.git
git push -u origin main
```

推送后回到 GitHub 仓库页面，确认：

- 根目录能看到 `metadata.yaml`、`main.py`、`_conf_schema.json`
- 文件不是嵌套在子目录里（**这是一个高频错误**：如果上传后根目录是 `astrbot_plugin_apex_stats/astrbot_plugin_apex_stats/main.py`，市场会拉取失败）

### 4.4 打标签与发布 GitHub Release（推荐）

插件市场按 `metadata.yaml` 的 `version` 判断更新，但打 tag 能让用户看到变更历史：

```bash
git tag -a v1.0.0 -m "v1.0.0: 首个版本"
git push origin v1.0.0
```

然后在 GitHub → Releases → **Draft a new release**：

- Tag 选 `v1.0.0`
- Title 填 `v1.0.0`
- 描述里粘贴变更摘要
- （可选）上传 `astrbot_plugin_apex_stats.zip` 作为附件，方便用户离线安装

> 注意：`metadata.yaml` 里的 `version` 是 `1.0.0`（无 `v`），Git tag 用 `v1.0.0`，两者不冲突，但**不要互相混用**。

---

## 5. 第五步：提交到插件市场

### 5.1 发布入口

1. 注册 / 登录 **AstrBot Cloud**：<https://cloud.astrbot.app/>
2. 打开插件发布页：<https://cloud.astrbot.app/publish>
3. 按表单填写插件信息（仓库地址、分类、标签等），提交

系统会**自动解析你仓库里的 `metadata.yaml`**，因此第 2 步的元数据准确性直接决定发布能否通过。

> 旧的 `AstrBotDevs/AstrBot_Plugins_Collection` 仓库已废弃，README 原文为「DEPRECATED, just summit your plugin at: https://cloud.astrbot.app/」，**不要再提 PR 到那个仓库**。

### 5.2 提交时要准备的信息

| 项 | 取值 |
| --- | --- |
| 仓库地址 | `https://github.com/your-github-name/astrbot_plugin_apex_stats` |
| 插件名 | `astrbot_plugin_apex_stats` |
| 展示名 | `Apex 战绩查询` |
| 短描述 | 发送 `/apex EA_ID` 即可查询 Apex Legends 玩家的等级、段位与击杀数据。 |
| 分类 | 游戏 / 查询 |
| 标签 | `游戏`、`查询`、`apex`、`Apex英雄` |
| 支持的 AstrBot 版本 | `>=4.0.0` |
| 是否开源 | 是（MIT） |

### 5.3 审核关注点

按官方开发原则，审核会关注：

- 功能是否经过测试
- 是否有良好的注释
- **持久化数据是否存放在 `data` 目录**而不是插件自身目录（本插件通过 `StarTools.get_data_dir()` 落盘到 `data/plugin_data/` ✅）
- 是否有良好的错误处理，不会因为一个错误导致插件崩溃
- 是否使用 `aiohttp` / `httpx` 等异步网络库（**禁止 `requests`**；本插件 httpx → aiohttp → urllib 三级降级 ✅）
- 是否用 ruff 格式化过
- 如果借鉴了其他项目，README 中是否说明了来源

---

## 6. 第六步：发布后的维护

### 6.1 发布新版本

```bash
# 1. 修改 metadata.yaml 的 version（例如 1.0.1）
# 2. 跑一遍自检与测试
python dev_check_release.py
python dev_selftest.py && python dev_test_client.py && python dev_test_plugin.py
ruff format . && ruff check .

# 3. 提交并推送
git add .
git commit -m "fix: 修复 xxx（v1.0.1）"
git push origin main

# 4. 打 tag 并发 Release
git tag -a v1.0.1 -m "v1.0.1: 修复 xxx"
git push origin v1.0.1
```

市场侧的更新检查依赖**已安装插件本地记录的来源**与市场记录中的 `version` 做比较，因此：

- **必须**在 `metadata.yaml` 里同步递增 `version`，只推代码不改版本号，用户不会收到更新提示
- 用户通过 zip 上传 / Git clone 安装的插件**不会**自动启用市场更新检查，除非显式绑定市场源

### 6.2 修改 `_conf_schema.json` 的注意事项

AstrBot 会递归比对 Schema 与用户已有配置：

- **新增**配置项 → 自动补默认值
- **删除**配置项 → 自动从用户配置中移除
- **重命名**配置键 → 用户旧值丢失，需要作为破坏性变更升 MAJOR 版本，并在 Release 说明里提醒重新配置

### 6.3 兼容性回归

每次改 API 解析逻辑前，先跑 `dev_selftest.py`；它内置了 v5 字典形态、旧版数组形态、`total` 对象形态三种真实字段结构，能挡住大部分解析回归。

---

## 7. 发布检查清单

发布前逐项打勾：

**身份与元数据**

- [ ] `metadata.yaml` 的 `author` 已替换（占位符 `your-github-name` 全部清除）
- [ ] `metadata.yaml` 的 `repo` 已替换为真实 GitHub 仓库地址
- [ ] `name` 全小写、以 `astrbot_plugin_` 开头、与仓库名一致
- [ ] `version` 为语义化版本且无 `v` 前缀，且**本次有递增**
- [ ] `astrbot_version` 无 `v` 前缀
- [ ] `support_platforms` 全部是官方合法 key
- [ ] `LICENSE` 中的版权人已替换

**代码质量**

- [ ] `python dev_check_release.py` 通过
- [ ] `python dev_selftest.py` / `dev_test_client.py` / `dev_test_plugin.py` 全部通过
- [ ] `ruff format .` 与 `ruff check .` 均无问题
- [ ] 仓库内无真实 API Key、无 `.env`
- [ ] `.gitignore` 生效：`data/`、`__pycache__/`、`*.zip` 未被提交

**仓库结构**

- [ ] GitHub 仓库**根目录**能看到 `metadata.yaml`
- [ ] 已打 tag 并发布 Release（可选但推荐）
- [ ] 仓库为 Public

**真机验证**

- [ ] 在真实 AstrBot 上重载插件无报错
- [ ] `/apex help`、`/apex <EA ID>`、`bind`/`unbind` 全流程可用
- [ ] 段位图标能显示（或已按需关闭 `enable_rank_image`）

**市场提交**

- [ ] 已在 <https://cloud.astrbot.app/publish> 提交
- [ ] 提交信息与 `metadata.yaml` 一致

---

## 8. 常见问题与排错

### 发布被拒绝：体积超过 16 MB

```bash
# 找出体积最大的文件
git ls-files | xargs du -h 2>/dev/null | sort -rh | head -20
```

对策：压缩图片资源、清理 `__pycache__` / `.git` / `node_modules`、精简依赖、用 `.gitattributes` 只发布必要文件。

### 市场安装失败：找不到 `metadata.yaml`

检查仓库根目录是否直接包含 `metadata.yaml`。常见错误是上传时多包了一层目录：

```
# 错误结构
astrbot_plugin_apex_stats/astrbot_plugin_apex_stats/metadata.yaml

# 正确结构
astrbot_plugin_apex_stats/metadata.yaml
```

### 安装后插件未加载 / WebUI 显示「加载失败」

1. WebUI → 插件页 → `加载失败插件` 列表，点 `重载` 查看报错
2. 检查 `astrbot_version` 约束是否过严（例如用户是 4.0.0，而约束写了 `>=4.17.0`）
3. 检查 `import` 是否使用了当前版本不存在的 API（本插件对 `astrbot.api.star` / `astrbot.core.star` 双路径做了兼容）

### 用户反馈「没有找到该玩家」

这不是插件 bug，而是数据源特性：PC 平台必须填 **EA / Origin 账号名**，Steam 昵称无效。README 已说明，FAQ 里可以再补一句。

### 用户反馈「图片发不出来」

部分平台适配器不支持图片消息。让用户在插件配置中关闭 `enable_rank_image`，文本战绩不受影响。

### 用户反馈「频繁限流」

免费 API Key 有速率限制。插件已内置 1 次/秒节流 + `X-Current-Rate` 自适应 + 默认 5 分钟缓存；可建议用户调大 `cache_ttl`。

### 改名后查不到玩家

插件已做 UID 记忆：首次查询成功后会把名字→UID 映射写入缓存（`data/plugin_data/...`），后续优先按 UID 查询，玩家改名不影响。若用户删过缓存，重新查一次名字即可恢复。

---

## 9. 本手册的信息来源与未确认项

**已核实（官方一手来源）**

- 发布流程、`metadata.yaml` 字段、16 MB 限制、平台适配器列表、开发原则：[AstrBot 发布插件到插件市场](https://docs.astrbot.app/dev/star/plugin-publish.html)、[AstrBot 插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html)
- 插件身份定义（`author/name`）、市场 JSON 校验规则、`repo` 允许的 URL 形式：[AstrBot 插件市场 JSON 规范 2026-06-27](https://docs.astrbot.app/dev/plugin-market/2026-06-27.html)
- 旧仓库已废弃：[AstrBotDevs/AstrBot_Plugins_Collection](https://github.com/AstrBotDevs/AstrBot_Plugins_Collection)（README 原文 `DEPRECATED, just summit your plugin at: https://cloud.astrbot.app/`）
- `StarTools.get_data_dir()` 语义、`AstrBotConfig` 注入条件（存在 `_conf_schema.json` 时才注入 `config`）：AstrBot 源码与官方存储文档

**未确认（以官方发布页实际表单为准）**

- 发布页表单的**具体字段与必填项**（`cloud.astrbot.app/publish` 需登录，无法抓取）
- 审核时长、是否有人工审核环节
- 版本号是否强制无 `v` 前缀（官方文档示例为无前缀；实际观察到部分已发布插件使用 `v1.0.1`，建议跟随官方示例）
- `logo` 字段与 `logo.png` 的优先级关系

---

**相关文档**

- [README.md](README.md) — 用户使用说明
- [metadata.yaml](metadata.yaml) — 待替换的元数据
- [dev_check_release.py](dev_check_release.py) — 发布前自检脚本
