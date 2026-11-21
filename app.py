# -*- coding: utf-8 -*-
"""云端部署入口（Streamlit Cloud / 魔搭创空间等默认入口文件）。

本地仍用 `streamlit run app/ui.py`；平台若要求根目录入口，用本文件即可：
    streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ui import main  # noqa: E402

if __name__ == "__main__":
    main()
