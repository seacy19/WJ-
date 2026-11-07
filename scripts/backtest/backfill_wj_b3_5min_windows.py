"""Fetch 5-minute bars only for WJ B3 candidate execution windows.

The API token is read from WJ_API_TOKEN and is never written to disk.
Raw minute bars are cached under data/ and should not be committed to Git.
"""

from __future__ import annotations

import concurrent.futures
import gzip
import json
import os
import random
import sys
import threading
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]  # 仓库根目录（脚本位于 scripts/backtest/ 下）
RESULTS = ROOT / "wj_backtest_results_2016_2025_leader_filter_trail5"
SIGNALS = RESULTS / "b3_signals.csv"
CURVE = RESULTS / "b3_equity_curve.csv"
OUT = ROOT / "data" / "wj_backtest_5min_b3"
API_URL = "https://t.xiaodefa.top/"
FREQ = "5min"
MAX_HOLD_SESSIONS = 7
WORKERS = int(os.environ.get("WJ_5MIN_WORKERS", "8"))

_thread_local = threading.local()


def get_api():
    if not hasattr(_thread_local, "api"):
        token = os.environ.get("WJ_API_TOKEN")
        if not token:
            raise RuntimeError("WJ_API_TOKEN is not set")
        sys.path.insert(0, str(ROOT / ".tushare_runtime"))
        import tushare as ts

        api = ts.pro_api(token)
        api._DataApi__http_url = API_URL
        _thread_local.api = (ts, api)
    return _thread_local.api


def make_jobs() -> list[dict]:
    signals = pd.read_csv(SIGNALS, encoding="utf-8-sig", dtype={"signal_date": str, "code": str})
    dates = pd.read_csv(CURVE, encoding="utf-8-sig", dtype={"trade_date": str})["trade_date"].tolist()
    date_to_loc = {date: i for i, date in enumerate(dates)}
    jobs = []
    for row in signals.itertuples(index=False):
        signal_date = str(row.signal_date).zfill(8)
        code = str(row.code)
        loc = date_to_loc.get(signal_date)
        if loc is None or loc + 1 >= len(dates):
            continue
        entry_loc = loc + 1
        end_loc = min(entry_loc + MAX_HOLD_SESSIONS - 1, len(dates) - 1)
        start_date, end_date = dates[entry_loc], dates[end_loc]
        out_file = OUT / f"year={signal_date[:4]}" / f"{code}_{signal_date}.csv.gz"
        jobs.append(
            {
                "signal_date": signal_date,
                "code": code,
                "start_date": start_date,
                "end_date": end_date,
                "out_file": out_file,
            }
        )
    return jobs


def fetch_one(job: dict) -> dict:
    path: Path = job["out_file"]
    if path.exists() and path.stat().st_size > 32:
        try:
            cached = pd.read_csv(path, compression="gzip", dtype={"ts_code": str})
            if len(cached):
                return {**job, "status": "cached", "rows": len(cached)}
        except Exception:
            pass

    ts, api = get_api()
    start = pd.Timestamp(job["start_date"]).strftime("%Y-%m-%d") + " 09:30:00"
    end = pd.Timestamp(job["end_date"]).strftime("%Y-%m-%d") + " 15:00:00"
    last_error = ""
    for attempt in range(5):
        try:
            frame = ts.pro_bar(
                api=api,
                ts_code=job["code"],
                freq=FREQ,
                start_date=start,
                end_date=end,
            )
            if frame is None:
                frame = pd.DataFrame()
            if len(frame):
                frame = frame.drop_duplicates(["ts_code", "trade_time"]).sort_values("trade_time")
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".tmp")
                frame.to_csv(tmp, index=False, compression="gzip", encoding="utf-8")
                tmp.replace(path)
            return {**job, "status": "ok" if len(frame) else "empty", "rows": len(frame)}
        except Exception as exc:
            last_error = type(exc).__name__
            if attempt < 4:
                time.sleep(min(8.0, 0.5 * (2**attempt)) + random.random() * 0.25)
    return {**job, "status": "error", "rows": 0, "error_type": last_error}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = make_jobs()
    results = []
    total = len(jobs)
    print(f"5MIN_JOBS {total} workers={WORKERS}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_one, job) for job in jobs]
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            if done % 50 == 0 or done == total:
                ok = sum(r["status"] in ("ok", "cached") for r in results)
                empty = sum(r["status"] == "empty" for r in results)
                errors = sum(r["status"] == "error" for r in results)
                rows = sum(r["rows"] for r in results)
                print(
                    f"PROGRESS {done}/{total} ok={ok} empty={empty} errors={errors} bars={rows:,}",
                    flush=True,
                )

    status_path = OUT / "fetch_status.json"
    safe_results = [
        {k: (str(v) if isinstance(v, Path) else v) for k, v in row.items()}
        for row in results
    ]
    status_path.write_text(
        json.dumps(
            {
                "frequency": FREQ,
                "signals": total,
                "ok_or_cached": sum(r["status"] in ("ok", "cached") for r in results),
                "empty": sum(r["status"] == "empty" for r in results),
                "errors": sum(r["status"] == "error" for r in results),
                "rows": sum(r["rows"] for r in results),
                "jobs": safe_results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"STATUS {status_path}", flush=True)


if __name__ == "__main__":
    main()
