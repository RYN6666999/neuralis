#!/usr/bin/env python3
"""
aris_tulpa_api — 薄殼版（2026-08-28）

⚠️ 所有邏輯已移至 tulpa/ 套件。
  引擎 → tulpa.engine / tulpa.evolution / tulpa.domain / tulpa.search
  API  → tulpa.api (此殼只做入口轉發)
原始檔 2597 行 → 薄殼 15 行。
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tulpa.tulpa_api import main
main()