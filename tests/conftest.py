"""pytest 全局配置（qa-tester 写区）。

职责：
1. 把项目根目录与 tests/ 目录加入 ``sys.path``，保证裸跑 ``pytest`` 时也能
   ``import app.*`` 与 ``import _support``（不依赖 ``python -m pytest``）。
2. 注册 ``llm`` 标记；默认跳过所有 ``@pytest.mark.llm`` 用例（无网/无 API key
   环境必须全绿）。需要真实跑 LLM 分支时用 ``RUN_LLM=1`` 或 ``pytest -m llm``。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "llm: 需要 DEEPSEEK_API_KEY 与联网，默认跳过（RUN_LLM=1 或 pytest -m llm 启用）",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    markexpr = str(config.getoption("markexpr") or "")
    run_llm = os.environ.get("RUN_LLM", "").strip().lower() in {"1", "true", "yes", "on"}
    if run_llm or "llm" in markexpr:
        return
    skip = pytest.mark.skip(
        reason="LLM 分支默认跳过（无网/无 key 约束）；设 RUN_LLM=1 或 pytest -m llm 启用"
    )
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
