"""配置：从环境变量 / .env 读取，供 qa、store、ui 共用。

用法：
    from app.config import load_settings
    s = load_settings()
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """优先用 python-dotenv；不可用时做极简解析（KEY=VALUE）。"""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=str(path), override=False)
        return
    except Exception:
        pass
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@dataclass
class Settings:
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    graph_backend: str = "local"
    data_dir: str = ""
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    ui_port: int = 8501
    ui_large_font: bool = False
    top_k: int = 6
    raw: dict = field(default_factory=dict)

    @property
    def llm_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve() if self.data_dir else ROOT / "data"


def load_settings(env_file: str | Path | None = None) -> Settings:
    env_path = Path(env_file) if env_file else ROOT / ".env"
    _load_dotenv(env_path)

    def _get(*names: str, default: str = "") -> str:
        for n in names:
            v = os.environ.get(n)
            if v is not None and v != "":
                return v
        return default

    return Settings(
        deepseek_api_key=_get("DEEPSEEK_API_KEY"),
        deepseek_model=_get("DEEPSEEK_MODEL", default="deepseek-chat"),
        deepseek_base_url=_get("DEEPSEEK_BASE_URL", default="https://api.deepseek.com"),
        graph_backend=_get("GRAPH_BACKEND", default="local").strip().lower(),
        data_dir=_get("DATA_DIR", default=str(ROOT / "data")),
        neo4j_uri=_get("NEO4J_URI", default="bolt://127.0.0.1:7687"),
        neo4j_user=_get("NEO4J_USER", default="neo4j"),
        neo4j_password=_get("NEO4J_PASSWORD"),
        ui_port=int(_get("UI_PORT", default="8501") or 8501),
        ui_large_font=_get("UI_LARGE_FONT", default="false").lower() in ("1", "true", "yes", "on"),
        top_k=int(_get("UI_TOPK", default="6") or 6),
    )
