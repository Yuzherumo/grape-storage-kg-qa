"""配置：从环境变量 / .env 读取，供 qa、store、ui 共用。

用法：
    from app.config import load_settings
    s = load_settings()

校验策略：模块 import 阶段不做任何校验；只有 ``load_settings()`` 读到非法值时才抛
``ConfigError``（``ValueError`` 子类），消息里带变量名、原值与合法范围，便于 UI/CLI 直接展示。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: GRAPH_BACKEND 的合法取值（保持既有默认 "local"）
GRAPH_BACKENDS = ("local", "neo4j")


class ConfigError(ValueError):
    """配置值非法：消息包含变量名、原值与合法范围；合法配置不会抛出。"""


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
    llm_timeout: float = 20.0
    raw: dict = field(default_factory=dict)

    @property
    def llm_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve() if self.data_dir else ROOT / "data"


def _parse_int(name: str, raw: str, *, default: int, minimum: int, maximum: int) -> int:
    """解析整数配置：空值用默认值；非整数或越界抛 ConfigError（消息含变量名/原值/范围）。"""
    text = raw.strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        raise ConfigError(
            f"{name} 配置非法：{raw!r}（要求整数，合法范围 {minimum}~{maximum}；留空则用默认值 {default}）"
        ) from None
    if not minimum <= value <= maximum:
        raise ConfigError(
            f"{name} 配置非法：{raw!r}（要求整数，合法范围 {minimum}~{maximum}；留空则用默认值 {default}）"
        )
    return value


def _parse_float(name: str, raw: str, *, default: float, minimum: float, maximum: float) -> float:
    """解析浮点配置：空值用默认值；非数值/NaN/越界抛 ConfigError。"""
    text = raw.strip()
    if not text:
        return default
    try:
        value = float(text)
    except ValueError:
        raise ConfigError(
            f"{name} 配置非法：{raw!r}（要求数值，合法范围 {minimum:g} < 值 ≤ {maximum:g}；留空则用默认值 {default:g}）"
        ) from None
    # NaN / inf 会走到 not(...) 分支，统一按非法处理
    if not (minimum < value <= maximum):
        raise ConfigError(
            f"{name} 配置非法：{raw!r}（要求数值，合法范围 {minimum:g} < 值 ≤ {maximum:g}；留空则用默认值 {default:g}）"
        )
    return value


def _parse_choice(name: str, raw: str, *, default: str, choices: tuple[str, ...]) -> str:
    """解析枚举配置：strip().lower() 后必须命中 choices；空值用默认值。"""
    text = raw.strip().lower()
    if not text:
        return default
    if text not in choices:
        raise ConfigError(
            f"{name} 配置非法：{raw!r}（合法取值：{' / '.join(choices)}；留空则用默认值 {default}）"
        )
    return text


def load_settings(env_file: str | Path | None = None) -> Settings:
    env_path = Path(env_file) if env_file else ROOT / ".env"
    _load_dotenv(env_path)

    def _get(*names: str, default: str = "") -> str:
        for n in names:
            v = os.environ.get(n)
            if v is not None and v.strip() != "":
                return v
        return default

    return Settings(
        deepseek_api_key=_get("DEEPSEEK_API_KEY"),
        deepseek_model=_get("DEEPSEEK_MODEL", default="deepseek-chat"),
        deepseek_base_url=_get("DEEPSEEK_BASE_URL", default="https://api.deepseek.com"),
        graph_backend=_parse_choice(
            "GRAPH_BACKEND",
            _get("GRAPH_BACKEND", default="local"),
            default="local",
            choices=GRAPH_BACKENDS,
        ),
        data_dir=_get("DATA_DIR", default=str(ROOT / "data")),
        neo4j_uri=_get("NEO4J_URI", default="bolt://127.0.0.1:7687"),
        neo4j_user=_get("NEO4J_USER", default="neo4j"),
        neo4j_password=_get("NEO4J_PASSWORD"),
        ui_port=_parse_int(
            "UI_PORT", _get("UI_PORT", default="8501"), default=8501, minimum=1, maximum=65535
        ),
        ui_large_font=_get("UI_LARGE_FONT", default="false").strip().lower() in ("1", "true", "yes", "on"),
        top_k=_parse_int("UI_TOPK", _get("UI_TOPK", default="6"), default=6, minimum=1, maximum=50),
        llm_timeout=_parse_float(
            "LLM_TIMEOUT",
            _get("LLM_TIMEOUT", default="20"),
            default=20.0,
            minimum=0.0,
            maximum=600.0,
        ),
    )
