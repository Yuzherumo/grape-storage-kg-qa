"""配置校验回归（task-5）：非法值抛 ConfigError、默认值不变、隔离真实 .env。

隔离策略：
- 每个用例只读仓库内 ``.tmp/`` 下的临时 env 文件（沙箱内 pytest 默认 tmp_path
  落在不可写目录，故不用 tmp_path），并显式清理 ``CONFIG_ENV_KEYS``，不依赖仓库
  真实 ``.env`` 的内容；
- autouse fixture 快照/恢复 ``os.environ``：python-dotenv 会把 env 文件写进进程
  环境，若不恢复，临时非法值会污染同进程里后续测试（真实 .env 已有
  UI_PORT / GRAPH_BACKEND 等键）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import ConfigError, Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]

#: load_settings 会读取的全部环境变量（清理后即回到 Settings 默认值）
CONFIG_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_BASE_URL",
    "GRAPH_BACKEND",
    "DATA_DIR",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "UI_PORT",
    "UI_LARGE_FONT",
    "UI_TOPK",
    "LLM_TIMEOUT",
)


@pytest.fixture(autouse=True)
def _restore_environ() -> Iterator[None]:
    """快照/恢复进程环境，抵消 python-dotenv 对 os.environ 的写入。"""
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


@pytest.fixture()
def env_dir() -> Iterator[Path]:
    """仓库 .tmp/ 下的临时目录（.gitignore 已忽略，且沙箱可写）。"""
    path = ROOT / ".tmp" / f"pytest-config-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def empty_env_file(env_dir: Path) -> Path:
    """临时空 env 文件：阻止 load_settings 去读仓库真实 .env。"""
    path = env_dir / "empty.env"
    path.write_text("", encoding="utf-8")
    return path


def _clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _assert_invalid(
    monkeypatch: pytest.MonkeyPatch,
    env_file: Path,
    name: str,
    value: str,
) -> str:
    """设置非法变量 → load_settings 必须抛 ConfigError，且消息含变量名与原值。"""
    _clear_config_env(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as caught:
        load_settings(env_file=env_file)
    message = str(caught.value)
    assert name in message, f"错误信息应包含变量名 {name}：{message!r}"
    assert value in message, f"错误信息应包含原值 {value!r}：{message!r}"
    return message


# ---------------------------------------------------------------- 契约
def test_config_error_is_value_error() -> None:
    assert issubclass(ConfigError, ValueError), "ConfigError 必须是 ValueError 子类（兼容既有 except ValueError）"


def test_settings_field_names_and_defaults_unchanged() -> None:
    """接口契约：Settings 字段名与默认值不得变化。"""
    settings = Settings()
    assert settings.deepseek_api_key == ""
    assert settings.deepseek_model == "deepseek-chat"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.graph_backend == "local"
    assert settings.data_dir == ""
    assert settings.neo4j_uri == "bolt://127.0.0.1:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_password == ""
    assert settings.ui_port == 8501
    assert settings.ui_large_font is False
    assert settings.top_k == 6
    assert settings.llm_timeout == 20.0
    assert settings.raw == {}
    assert set(Settings.__dataclass_fields__) >= {
        "deepseek_api_key",
        "deepseek_model",
        "deepseek_base_url",
        "graph_backend",
        "data_dir",
        "neo4j_uri",
        "neo4j_user",
        "neo4j_password",
        "ui_port",
        "ui_large_font",
        "top_k",
        "llm_timeout",
        "raw",
    }


# ---------------------------------------------------------------- 默认值 / 合法覆盖
def test_defaults_with_isolated_empty_env_file(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path) -> None:
    _clear_config_env(monkeypatch)
    settings = load_settings(env_file=empty_env_file)
    assert settings.ui_port == 8501
    assert settings.top_k == 6
    assert settings.llm_timeout == 20.0
    assert settings.graph_backend == "local"
    assert settings.ui_large_font is False


def test_legal_values_override(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path) -> None:
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("UI_PORT", "8600")
    monkeypatch.setenv("UI_TOPK", "12")
    monkeypatch.setenv("LLM_TIMEOUT", "7.5")
    monkeypatch.setenv("GRAPH_BACKEND", " Neo4j ")
    monkeypatch.setenv("UI_LARGE_FONT", "yes")
    settings = load_settings(env_file=empty_env_file)
    assert settings.ui_port == 8600
    assert settings.top_k == 12
    assert settings.llm_timeout == 7.5
    assert settings.graph_backend == "neo4j", "GRAPH_BACKEND 应 strip().lower() 后归一"
    assert settings.ui_large_font is True


def test_boundary_values_are_accepted(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path) -> None:
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("UI_PORT", "1")
    monkeypatch.setenv("UI_TOPK", "50")
    monkeypatch.setenv("LLM_TIMEOUT", "600")
    settings = load_settings(env_file=empty_env_file)
    assert (settings.ui_port, settings.top_k, settings.llm_timeout) == (1, 50, 600.0)


def test_blank_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path) -> None:
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("UI_PORT", "   ")
    monkeypatch.setenv("UI_TOPK", "")
    monkeypatch.setenv("LLM_TIMEOUT", "  ")
    monkeypatch.setenv("GRAPH_BACKEND", "   ")
    settings = load_settings(env_file=empty_env_file)
    assert (settings.ui_port, settings.top_k, settings.llm_timeout) == (8501, 6, 20.0)
    assert settings.graph_backend == "local"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1", True),
        ("TRUE", True),
        ("yes", True),
        ("On", True),
        ("0", False),
        ("no", False),
        ("false", False),
        ("随便什么", False),
    ],
)
def test_ui_large_font_stays_loose(
    monkeypatch: pytest.MonkeyPatch, empty_env_file: Path, raw: str, expected: bool
) -> None:
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("UI_LARGE_FONT", raw)
    assert load_settings(env_file=empty_env_file).ui_large_font is expected


# ---------------------------------------------------------------- 四类非法配置
@pytest.mark.parametrize("value", ["0", "-1", "70000", "abc", "8501.5"])
def test_invalid_ui_port(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path, value: str) -> None:
    message = _assert_invalid(monkeypatch, empty_env_file, "UI_PORT", value)
    assert "1~65535" in message, f"错误信息应给出合法范围 1~65535：{message!r}"


@pytest.mark.parametrize("value", ["0", "-3", "99", "abc"])
def test_invalid_ui_topk(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path, value: str) -> None:
    message = _assert_invalid(monkeypatch, empty_env_file, "UI_TOPK", value)
    assert "1~50" in message, f"错误信息应给出合法范围 1~50：{message!r}"


@pytest.mark.parametrize("value", ["0", "-1", "abc", "nan", "inf"])
def test_invalid_llm_timeout(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path, value: str) -> None:
    message = _assert_invalid(monkeypatch, empty_env_file, "LLM_TIMEOUT", value)
    assert "600" in message, f"错误信息应给出上限 600：{message!r}"


@pytest.mark.parametrize("value", ["foo", "mysql", "LOCAL2"])
def test_invalid_graph_backend(monkeypatch: pytest.MonkeyPatch, empty_env_file: Path, value: str) -> None:
    message = _assert_invalid(monkeypatch, empty_env_file, "GRAPH_BACKEND", value)
    assert "local" in message and "neo4j" in message, f"错误信息应列出合法取值：{message!r}"


# ---------------------------------------------------------------- 临时 env 文件隔离
def test_temp_env_file_is_used_and_can_override(monkeypatch: pytest.MonkeyPatch, env_dir: Path) -> None:
    _clear_config_env(monkeypatch)
    env_file = env_dir / "custom.env"
    env_file.write_text(
        "UI_PORT=8601\nUI_TOPK=9\nLLM_TIMEOUT=12.5\nGRAPH_BACKEND=Neo4j\nUI_LARGE_FONT=ON\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file=env_file)
    assert settings.ui_port == 8601
    assert settings.top_k == 9
    assert settings.llm_timeout == 12.5
    assert settings.graph_backend == "neo4j"
    assert settings.ui_large_font is True


def test_invalid_value_from_env_file_raises(monkeypatch: pytest.MonkeyPatch, env_dir: Path) -> None:
    _clear_config_env(monkeypatch)
    env_file = env_dir / "bad.env"
    env_file.write_text("GRAPH_BACKEND=foo\n", encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_settings(env_file=env_file)
    assert "GRAPH_BACKEND" in str(caught.value)


def test_invalid_env_values_do_not_break_import() -> None:
    """A4：import 阶段不得因非法配置崩溃，只有 load_settings() 才抛 ConfigError。"""
    code = (
        "import app.config as config\n"
        "print('import-ok')\n"
        "try:\n"
        "    config.load_settings()\n"
        "except config.ConfigError as exc:\n"
        "    print('config-error', 'UI_PORT' in str(exc))\n"
    )
    env = {**os.environ, "UI_PORT": "abc", "LLM_TIMEOUT": "not-a-number"}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    output = (proc.stdout or b"").decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"import 阶段崩溃（退出码 {proc.returncode}）：\n{output}"
    assert "import-ok" in output, f"import 阶段应成功：\n{output}"
    assert "config-error True" in output, f"load_settings() 应抛 ConfigError 且消息含 UI_PORT：\n{output}"
