"""Launch the offline cloud-panel WJ backtest without using a stored token."""

from __future__ import annotations

import os
import runpy

os.environ["TUSHARE_TOKEN"] = "cache-only-no-api-calls"
runpy.run_path(
    "/home/ubuntu/ww-cache/wj_long_backtest/run_wj_long_backtest_cloud.py",
    run_name="__main__",
)
