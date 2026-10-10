"""发布前自检：校验 metadata.yaml、_conf_schema.json、目录结构、体积与占位符。

用法：
    python dev_check_release.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 与 AstrBot 官方 metadata.yaml 要求对齐
REQUIRED_FIELDS = ("name", "desc", "version", "author", "repo")
OPTIONAL_FIELDS = (
    "display_name",
    "short_desc",
    "astrbot_version",
    "support_platforms",
    "social_link",
    "tags",
    "logo",
)
# 官方文档给出的合法平台适配器 key
VALID_PLATFORMS = {
    "aiocqhttp",
    "qq_official",
    "qq_official_webhook",
    "telegram",
    "wecom",
    "wecom_ai_bot",
    "lark",
    "dingtalk",
    "discord",
    "slack",
    "kook",
    "vocechat",
    "weixin_official_account",
    "weixin_oc",
    "satori",
    "misskey",
    "line",
    "matrix",
    "mattermost",
}
REPO_PATTERN = re.compile(r"^https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:\.git|/tree/[A-Za-z0-9_-]+)?$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
MAX_ZIP_BYTES = 16 * 1024 * 1024


def load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        # 退化：支持 key: value 与简单列表的最小解析器，避免自检依赖 PyYAML
        data: dict = {}
        current_key = ""
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            stripped = raw_line.strip()
            if stripped.startswith("- "):
                if current_key:
                    data.setdefault(current_key, [])
                    if isinstance(data[current_key], list):
                        data[current_key].append(stripped[2:].strip().strip("\"'"))
                continue
            if raw_line[0].isspace() or raw_line.startswith("|"):
                continue  # 多行文本 / 嵌套内容，自检不解析
            key, _, value = raw_line.partition(":")
            current_key = key.strip()
            data[current_key] = value.strip().strip("\"'")
        return data
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    # 1) metadata.yaml
    meta_path = HERE / "metadata.yaml"
    if not meta_path.exists():
        problems.append("缺少 metadata.yaml（AstrBot 依赖它识别插件）")
        meta: dict = {}
    else:
        try:
            meta = load_yaml(meta_path) or {}
        except Exception as exc:  # noqa: BLE001
            problems.append(f"metadata.yaml 解析失败：{exc}")
            meta = {}

    for field in REQUIRED_FIELDS:
        if not meta.get(field):
            problems.append(f"metadata.yaml 缺少必填字段：{field}")

    name = str(meta.get("name", ""))
    if name and not name.startswith("astrbot_plugin_"):
        warnings.append(f"插件名 `{name}` 未以 astrbot_plugin_ 开头（官方推荐）")
    if name and name != name.lower():
        warnings.append(f"插件名 `{name}` 含大写字母（官方要求全小写）")
    if " " in name:
        problems.append(f"插件名 `{name}` 不能包含空格")
    if name and name != HERE.name:
        warnings.append(f"metadata.name（{name}）与目录名（{HERE.name}）不一致，市场安装会按 metadata.name 识别")

    version = str(meta.get("version", ""))
    if version and not SEMVER_PATTERN.match(version):
        warnings.append(f"version `{version}` 不是语义化版本（官方示例为 1.0.0，不要加 v 前缀）")

    repo = str(meta.get("repo", ""))
    if repo and not REPO_PATTERN.match(repo):
        problems.append(f"repo 必须是 https://github.com/<owner>/<repo> 形式，当前为：{repo}")
    if "your-github-name" in repo or str(meta.get("author", "")) == "your-github-name":
        warnings.append("repo / author 仍是占位符 your-github-name，发布前必须替换")

    platforms = meta.get("support_platforms") or []
    if not isinstance(platforms, list):
        problems.append("support_platforms 必须是列表")
    else:
        invalid = [p for p in platforms if p not in VALID_PLATFORMS]
        if invalid:
            problems.append(f"support_platforms 含非法平台 key：{invalid}")

    astrbot_version = str(meta.get("astrbot_version", ""))
    if astrbot_version and astrbot_version.startswith("v"):
        problems.append(f"astrbot_version 不要加 v 前缀：{astrbot_version}")

    unknown = set(meta) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
    if unknown:
        warnings.append(f"metadata.yaml 含未知字段（可能被忽略）：{sorted(unknown)}")

    # 2) _conf_schema.json
    schema_path = HERE / "_conf_schema.json"
    if not schema_path.exists():
        warnings.append("没有 _conf_schema.json，AstrBot 不会为插件注入 config 参数")
    else:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if not isinstance(schema, dict):
                problems.append("_conf_schema.json 顶层必须是对象")
            else:
                for key, item in schema.items():
                    if not isinstance(item, dict) or "type" not in item:
                        problems.append(f"_conf_schema.json 的 {key} 缺少必填的 type 字段")
                    if item.get("type") == "object" and "items" not in item:
                        warnings.append(f"_conf_schema.json 的 {key} 是 object 类型但缺少 items")
        except json.JSONDecodeError as exc:
            problems.append(f"_conf_schema.json 不是合法 JSON：{exc}")

    # 3) 必需文件
    for filename in ("main.py", "README.md"):
        if not (HERE / filename).exists():
            problems.append(f"缺少 {filename}")

    # 4) 体积与脏文件
    total = 0
    dirty: list[str] = []
    for path in HERE.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(HERE).as_posix()
        if "__pycache__" in relative or relative.endswith(".pyc"):
            dirty.append(relative)
            continue
        total += path.stat().st_size
    if total > MAX_ZIP_BYTES:
        problems.append(f"插件体积 {total / 1048576:.1f} MB 超过市场 16MB 上限")
    if dirty:
        warnings.append(f"存在编译缓存文件，发布前应删除：{dirty[:5]}")

    # 5) 输出
    print(f"插件名：{name}｜版本：{version}｜作者：{meta.get('author')}")
    print(f"体积：{total / 1024:.0f} KB（上限 16 MB）")
    print(f"支持平台：{len(platforms)} 个")
    for warning in warnings:
        print(f"  [警告] {warning}")
    for problem in problems:
        print(f"  [错误] {problem}")
    if problems:
        print(f"\n❌ 发现 {len(problems)} 个必须修复的问题")
        return 1
    print(f"\n✅ 发布前自检通过（{len(warnings)} 条提醒）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
