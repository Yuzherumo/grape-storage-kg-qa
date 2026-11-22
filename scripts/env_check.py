"""环境自检：Python/依赖版本、GRAPH_BACKEND、图谱后端可用性、LLM 可用性 → docs/env_check.md。

用法（项目根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\env_check.py

说明：只读取环境变量与本地文件，**不联网**。LLM「可用性」仅判断是否配置了
DEEPSEEK_API_KEY 且客户端可构造，不发起真实请求。
"""
from __future__ import annotations

import importlib
import importlib.metadata
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
GRAPH = ROOT / "graph"
DOCS = ROOT / "docs"
OUT_PATH = DOCS / "env_check.md"

DEPS = ["pytest", "streamlit", "openai", "pandas", "python-dotenv", "neo4j"]
DATA_FILES = [
    "entities.csv",
    "triples.csv",
    "sources.csv",
    "schema.json",
    "triples_shine_muscat.csv",
]
GRAPH_FILES = [
    "schema.cypher",
    "init_nodes.cypher",
    "init_rels.cypher",
]


def load_dotenv() -> str:
    """尝试加载项目根目录 .env（无 python-dotenv 时静默跳过）。"""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return "无 .env 文件"
    try:
        from dotenv import load_dotenv as _load  # type: ignore

        _load(env_path)
        return f"已加载 {env_path.name}"
    except Exception:  # noqa: BLE001
        return "发现 .env 但 python-dotenv 不可用，未加载"


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:  # noqa: BLE001
        pass
    module_name = name.replace("-", "_")
    try:
        module = importlib.import_module(module_name)
        return str(getattr(module, "__version__", "已安装(版本未知)"))
    except Exception:  # noqa: BLE001
        return "未安装"


def env_status(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return "未设置"
    if any(secret in name for secret in ("KEY", "PASSWORD", "TOKEN")):
        return "已设置（不显示值）"
    return f"`{value}`"


def graph_backend() -> str:
    try:
        from app import config as app_config

        loader = getattr(app_config, "load_settings", None) or getattr(app_config, "get_settings", None)
        if loader is not None:
            settings = loader()
            for attr in ("graph_backend", "GRAPH_BACKEND", "backend"):
                value = getattr(settings, attr, None)
                if value:
                    return str(value)
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("GRAPH_BACKEND", "local") or "local"


def check_local_graph() -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "message": "", "stats": {}}
    try:
        from app.store.local_store import LocalStore

        store = LocalStore(str(DATA))
        ok, message = store.health()
        result.update(ok=bool(ok), message=str(message), stats=store.stats())
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"LocalStore 不可用：{exc}"
    return result


def check_neo4j() -> str:
    driver = package_version("neo4j")
    if driver == "未安装":
        return "未安装 neo4j 驱动（可选，本地后端已足够离线演示）"
    uri = os.environ.get("NEO4J_URI", "")
    if not uri:
        return "已安装 neo4j 驱动，但未配置 NEO4J_URI"
    try:
        from app.store.neo4j_store import Neo4jStore

        store = Neo4jStore(uri, os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
        ok, message = store.health()
        return f"{'可达' if ok else '不可达'}：{message}"
    except Exception as exc:  # noqa: BLE001
        return f"连接失败（可回落 local）：{exc}"


def check_llm() -> dict[str, Any]:
    result: dict[str, Any] = {"available": None, "detail": ""}
    try:
        from app.llm import LLMClient

        client = LLMClient()
        result["available"] = bool(getattr(client, "available", False))
        model = str(getattr(client, "model", "") or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
        if result["available"]:
            result["detail"] = f"已配置 API key，模型 {model}（未发起真实请求）"
        else:
            result["detail"] = f"未配置 DEEPSEEK_API_KEY，问答自动走离线模板模式（模型 {model}）"
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"app.llm 不可用：{exc}"
    return result


def file_info(path: Path) -> str:
    if not path.is_file():
        return "缺失"
    try:
        lines = path.read_text(encoding="utf-8-sig").count("\n")
        return f"存在（{path.stat().st_size} B，{lines} 行）"
    except Exception:  # noqa: BLE001
        return "存在（无法读取）"


def render_report() -> str:
    dotenv_note = load_dotenv()
    local = check_local_graph()
    llm = check_llm()
    backend = graph_backend()
    offline_ready = bool(local["ok"])

    lines: list[str] = []
    lines.append("# 环境自检（docs/env_check.md）")
    lines.append("")
    lines.append("> 由 `scripts/env_check.py` 自动生成（不联网）。")
    lines.append("> 重新生成：`.\\.venv\\Scripts\\python.exe scripts\\env_check.py`")
    lines.append("")
    lines.append(f"- 采集时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 操作系统：`{platform.platform()}`")
    lines.append(f"- Python：`{sys.version.split()[0]}`（`{sys.executable}`）")
    lines.append(f"- 工作目录：`{Path.cwd()}`")
    lines.append(f"- .env：{dotenv_note}")
    lines.append("")

    lines.append("## 1. 依赖版本")
    lines.append("")
    lines.append("依赖 | 版本")
    lines.append("---|---")
    for name in DEPS:
        lines.append(f"{name} | {package_version(name)}")
    lines.append("")

    lines.append("## 2. 关键环境变量")
    lines.append("")
    lines.append("变量 | 状态")
    lines.append("---|---")
    for name in (
        "GRAPH_BACKEND",
        "DATA_DIR",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "UI_PORT",
    ):
        lines.append(f"{name} | {env_status(name)}")
    lines.append("")

    lines.append("## 3. 图谱后端")
    lines.append("")
    lines.append(f"- 配置后端（GRAPH_BACKEND）：`{backend}`")
    lines.append(f"- 本地后端可用性：{'✅ 可用' if local['ok'] else '❌ 不可用'} —— {local['message']}")
    if local.get("stats"):
        lines.append(f"- 图谱统计：`{local['stats']}`")
    lines.append(f"- Neo4j：{check_neo4j()}")
    lines.append("")

    lines.append("## 4. LLM 可用性（不发起真实请求）")
    lines.append("")
    if llm["available"] is True:
        lines.append(f"- 状态：✅ 可用 —— {llm['detail']}")
    elif llm["available"] is False:
        lines.append(f"- 状态：⭕ 不可用（预期行为）—— {llm['detail']}")
    else:
        lines.append(f"- 状态：❔ 未知 —— {llm['detail']}")
    lines.append("")

    lines.append("## 5. 数据与图谱文件")
    lines.append("")
    lines.append("文件 | 状态")
    lines.append("---|---")
    for name in DATA_FILES:
        lines.append(f"data/{name} | {file_info(DATA / name)}")
    for name in GRAPH_FILES:
        lines.append(f"graph/{name} | {file_info(GRAPH / name)}")
    queries_dir = GRAPH / "queries"
    if queries_dir.is_dir():
        count = len(list(queries_dir.glob("*.cypher")))
        lines.append(f"graph/queries/*.cypher | {count} 个查询模板")
    else:
        lines.append("graph/queries/*.cypher | 缺失")
    lines.append("")

    lines.append("## 6. 结论")
    lines.append("")
    if offline_ready:
        lines.append("- ✅ **无网络、无 API key 也能完成离线演示**：本地图谱后端可用，"
                     "LLM 不可用时问答自动走模板模式（答案仍带 `[E#]` 引用与分步动作）。")
    else:
        lines.append("- ❌ 本地图谱后端不可用：请检查 `data/entities.csv`、`data/triples.csv` 是否存在且列完整。")
    lines.append(f"- pytest：{package_version('pytest')}；运行全量测试：`.\\.venv\\Scripts\\python.exe -m pytest tests -q`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    report = render_report()
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"[env_check] 报告已写入：{OUT_PATH}")
    local = check_local_graph()
    print(f"[env_check] 本地图谱后端：{'可用' if local['ok'] else '不可用'}；{local['message']}")
    return 0 if local["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
