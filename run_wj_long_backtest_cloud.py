"""Run the existing WJ technical proxies on audited Tencent daily panels."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TUSHARE_TOKEN", "cache-only-no-api-calls")

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/ww-cache/wj_long_backtest")
SOURCE = ROOT / "backtest_wj_strategy.py"
PRICE_ROOT = ROOT / "prices"
BASIC_FILE = ROOT / "stock_basic_all.csv"
BENCHMARK_FILE = ROOT / os.environ.get("WJ_BENCHMARK_FILE", "index_benchmark_000985_CSI_2016_2025.csv")
RESULTS = ROOT / os.environ.get("WJ_RESULTS_SUBDIR", "results_2016_2025_clean_universe_technical_proxies")
LIMIT_JSON_ROOT = ROOT / "market_data_2016_2025" / "stk_limit"
LIMIT_PARQUET_ROOT = ROOT / "market_data_2016_2025" / "stk_limit_parquet"
MINUTE_ROOT = ROOT / os.environ.get("WJ_5MIN_ROOT", "market_data_5min_b3_windows")
DATA_START = os.environ.get("WJ_DATA_START", "20150101")
BACKTEST_START = os.environ.get("WJ_BACKTEST_START", "20160104")
END = os.environ.get("WJ_END", "20251231")


def load_strategy():
    spec = importlib.util.spec_from_file_location("wj_backtest_strategy", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load strategy source: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.RESULTS = RESULTS
    return module


def as_yyyymmdd(value, default: int) -> int:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return int(text[:8])


def load_daily(pd_module, basic: pd.DataFrame) -> pd.DataFrame:
    columns = ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]
    frames = []
    for year in range(int(DATA_START[:4]), int(END[:4]) + 1):
        folder = PRICE_ROOT / f"year={year}"
        year_frames = []
        for path in sorted(folder.glob("*.parquet")):
            frame = pd_module.read_parquet(path, columns=columns)
            frame = frame[(frame["trade_date"] >= DATA_START) & (frame["trade_date"] <= END)]
            if len(frame):
                year_frames.append(frame)
        del frame
        if not year_frames:
            continue
        year_data = pd_module.concat(year_frames, ignore_index=True)
        if 2016 <= year <= 2025:
            limit_data = load_limit_year(pd_module, year)
            year_data = year_data.merge(limit_data, on=["ts_code", "trade_date"], how="left", validate="one_to_one")
        else:
            year_data["up_limit"] = np.nan
        frames.append(year_data)
        print(f"LOADED_YEAR {year} cumulative_rows={sum(len(x) for x in frames):,}", flush=True)
    daily = pd_module.concat(frames, ignore_index=True)
    duplicates = int(daily.duplicated(["ts_code", "trade_date"]).sum())
    if duplicates:
        raise RuntimeError(f"price panel contains {duplicates} duplicate security-date rows")
    daily = daily.dropna(subset=["open", "high", "low", "close", "pct_chg", "vol", "amount"])
    for col in ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]:
        daily[col] = pd_module.to_numeric(daily[col], errors="coerce").astype("float32")
    daily["ts_code"] = daily["ts_code"].astype("category")
    daily.sort_values(["ts_code", "trade_date"], inplace=True, ignore_index=True)
    daily["trade_date"] = daily["trade_date"].astype(str)

    # Exclude historical rows before listing and after delisting. The cloud price
    # panel contains several vendor-era code mappings with pre-listing records.
    basic_by_code = basic.set_index("ts_code").to_dict("index")
    sys.path.insert(0, "/home/ubuntu/ww-cache/project")
    security_meta = pd_module.read_pickle("/home/ubuntu/ww-cache/proxy_cache/stock_metadata_v2.pkl")
    categories = daily["ts_code"].cat.categories.to_numpy()
    code_ids = daily["ts_code"].cat.codes.to_numpy()
    trade_dates = daily["trade_date"].astype("int32").to_numpy()
    boundaries = np.flatnonzero(np.r_[True, code_ids[1:] != code_ids[:-1], True])
    keep = np.ones(len(daily), dtype=bool)
    for lo, hi in zip(boundaries[:-1], boundaries[1:]):
        code = str(categories[code_ids[lo]])
        info = basic_by_code.get(code)
        if info is None:
            keep[lo:hi] = False
            continue
        list_date = as_yyyymmdd(info.get("list_date"), 19000101)
        delist_date = as_yyyymmdd(info.get("delist_date"), 99991231)
        group_dates = trade_dates[lo:hi]
        valid = (group_dates >= list_date) & (group_dates <= delist_date)
        meta = security_meta.get(code)
        if meta is not None:
            for st_start, st_end in meta.st_periods:
                start = as_yyyymmdd(st_start, 19000101)
                end = as_yyyymmdd(st_end, 99991231)
                valid &= ~((group_dates >= start) & (group_dates <= end))
        keep[lo:hi] = valid
    removed = int((~keep).sum())
    daily = daily.loc[keep].copy()
    print(
        f"PRICE_PANEL rows={len(daily):,} codes={daily['ts_code'].nunique():,} removed_prepostlist_or_st={removed:,} "
        f"period={daily['trade_date'].min()}..{daily['trade_date'].max()}", flush=True
    )
    return daily


def load_limit_year(pd_module, year: int) -> pd.DataFrame:
    parquet_path = LIMIT_PARQUET_ROOT / f"year={year}" / "daily.parquet"
    if not parquet_path.exists():
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for path in sorted(LIMIT_JSON_ROOT.glob("*.json")):
            if path.stem[:4] != str(year):
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            fields = payload["fields"]
            code_ix = fields.index("ts_code")
            up_ix = fields.index("up_limit")
            date_ix = fields.index("trade_date")
            for item in payload["items"]:
                rows.append((str(item[code_ix]), str(item[date_ix]), item[up_ix]))
        frame = pd_module.DataFrame(rows, columns=["ts_code", "trade_date", "up_limit"])
        frame["up_limit"] = pd_module.to_numeric(frame["up_limit"], errors="coerce").astype("float32")
        frame.to_parquet(parquet_path, index=False, compression="zstd")
        print(f"BUILT_LIMIT_PARQUET {year} rows={len(frame):,}", flush=True)
    return pd_module.read_parquet(parquet_path, columns=["ts_code", "trade_date", "up_limit"])


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    strategy = load_strategy()
    basic = pd.read_csv(
        BASIC_FILE,
        dtype={"ts_code": "string", "name": "string", "industry": "string", "list_date": "string", "delist_date": "string"},
        encoding="utf-8",
    )
    basic["name"] = basic["name"].fillna("").str.replace("ST", "", regex=False)
    basic["industry"] = basic["industry"].fillna("")
    basic["list_date"] = basic["list_date"].fillna("19000101")
    daily = load_daily(pd, basic)
    config = strategy.Config(
        data_start=DATA_START,
        backtest_start=BACKTEST_START,
        end=END,
        round_trip_cost=0.003,
        max_positions=10,
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    b3_signals, trend_signals, price_data, _all_a_daily = strategy.build_signals(daily, basic, config)
    print(f"SIGNALS b3={len(b3_signals):,} trend={len(trend_signals):,}", flush=True)

    index_data = pd.read_csv(BENCHMARK_FILE, dtype={"trade_date": "string"}, encoding="utf-8")
    index_data.sort_values("trade_date", inplace=True)
    expected_dates = sorted(d for d in daily["trade_date"].unique() if BACKTEST_START <= d <= END)
    if index_data["trade_date"].tolist() != expected_dates:
        raise RuntimeError("CSI All Share benchmark dates do not match the backtest calendar")
    index_data["pct_chg"] = pd.to_numeric(index_data["pct_chg"], errors="raise") / 100.0
    index_data.iloc[0, index_data.columns.get_loc("pct_chg")] = 0.0  # start at the first close
    market_daily = pd.Series(index_data["pct_chg"].to_numpy(), index=index_data["trade_date"].astype(str))

    b3_trades = strategy.run_trade_simulations(b3_signals, price_data, config, "b3")
    trend_trades = strategy.run_trade_simulations(trend_signals, price_data, config, "trend")
    strategy.add_benchmark_return(b3_trades, market_daily)
    strategy.add_benchmark_return(trend_trades, market_daily)
    b3_curve, b3_portfolio, b3_accepted = strategy.portfolio_curve(b3_trades, market_daily, config)
    trend_curve, trend_portfolio, trend_accepted = strategy.portfolio_curve(trend_trades, market_daily, config)

    b3_5min_results = {}
    if MINUTE_ROOT.exists():
        for trail_mode, suffix in [
            ("same_bar_peak_first", "same_bar_peak_first"),
            ("prior_bar_peak", "prior_bar_peak"),
        ]:
            trades, counts = strategy.run_b3_5min_trade_simulations(
                b3_signals, price_data, MINUTE_ROOT, config, trail_mode
            )
            strategy.add_benchmark_return(trades, market_daily)
            curve, portfolio, accepted = strategy.portfolio_curve(trades, market_daily, config)
            pd.DataFrame(strategy.serializable_trades(trades)).to_csv(
                RESULTS / f"b3_5min_{suffix}_trades.csv", index=False, encoding="utf-8-sig"
            )
            pd.DataFrame(strategy.serializable_trades(accepted)).to_csv(
                RESULTS / f"b3_5min_{suffix}_portfolio_trades.csv", index=False, encoding="utf-8-sig"
            )
            curve.to_csv(RESULTS / f"b3_5min_{suffix}_equity_curve.csv", encoding="utf-8-sig")
            b3_5min_results[suffix] = {
                "coverage": counts,
                "candidate_trade_metrics": strategy.trade_metrics(trades),
                "portfolio_metrics": portfolio,
            }
            print(
                f"5MIN {suffix} coverage={counts} portfolio={portfolio}",
                flush=True,
            )

    b3_signals.to_csv(RESULTS / "b3_signals.csv", index=False, encoding="utf-8-sig")
    trend_signals.to_csv(RESULTS / "trend_signals.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(strategy.serializable_trades(b3_trades)).to_csv(RESULTS / "b3_trades.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(strategy.serializable_trades(trend_trades)).to_csv(RESULTS / "trend_trades.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(strategy.serializable_trades(b3_accepted)).to_csv(RESULTS / "b3_portfolio_trades.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(strategy.serializable_trades(trend_accepted)).to_csv(RESULTS / "trend_portfolio_trades.csv", index=False, encoding="utf-8-sig")
    b3_curve.to_csv(RESULTS / "b3_equity_curve.csv", encoding="utf-8-sig")
    trend_curve.to_csv(RESULTS / "trend_equity_curve.csv", encoding="utf-8-sig")

    summary = {
        "config": config.__dict__,
        "data": {
            "rows": int(len(daily)),
            "codes": int(daily["ts_code"].nunique()),
            "first_date": str(daily["trade_date"].min()),
            "last_date": str(daily["trade_date"].max()),
            "price_source": str(PRICE_ROOT),
            "metadata_source": str(BASIC_FILE),
            "duplicates": 0,
        },
        "methodology": {
    "b3": "same-current-industry leader-break proxy + low-base/volume filters; leader-health gate: signal close drawdown from 10-session closing high <=15%, close >= MA5, next-session open >= prior MA5 and overnight gap > -5%; daily baseline uses next-open entry capped at +7%, while 5-minute B.5 execution enters next session at the first open <=+2% or at a +2% limit touch; -5% hard stop, all-out trailing exit on 5% drawdown from peak since entry, and short time/MA exits",
            "trend": "C.3/C.4 price/volume breakout proxy only; next-open entry; -8% initial stop and 20-day/platform exit; no fundamental screen",
            "universe": "rows outside listing/delisting dates and recorded historical ST intervals excluded; current name marker stripped to avoid excluding a security from all prior years",
            "industry": "current TuShare stock_basic industry used as a proxy, not historical WJ theme membership",
            "limit_up": "official historical stk_limit up_limit used when available; pct_chg threshold fallback only where that field is absent",
            "cost": "0.30% round trip per trade",
            "portfolio": "separate branch portfolios; max 10 positions each",
            "benchmark": f"CSI All Share index 000985.CSI daily returns from {BENCHMARK_FILE.name}; first backtest date starts at that session close",
            "mainline_labels": "weekly labels and fundamental criteria not used for selection because historical security/theme mapping and point-in-time fundamentals are unavailable",
        },
        "b3": {
            "signals": int(len(b3_signals)),
            "candidate_trade_metrics": strategy.trade_metrics(b3_trades),
            "portfolio_metrics": b3_portfolio,
        },
        "b3_5min": b3_5min_results,
        "trend": {
            "signals": int(len(trend_signals)),
            "candidate_trade_metrics": strategy.trade_metrics(trend_trades),
            "portfolio_metrics": trend_portfolio,
        },
    }
    save_json(RESULTS / "summary.json", summary)
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
