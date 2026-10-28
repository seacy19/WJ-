from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# The project-requested Tushare initialization is intentionally kept verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parent / ".tushare_runtime"))
import tushare as ts
import tushare.pro.client as client
client.DataApi._DataApi__http_url = "http://api.quicksync.cn"
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
if not TUSHARE_TOKEN:
    raise RuntimeError("Set TUSHARE_TOKEN or TUSHARE_PRO_TOKEN before requesting market data.")
pro = ts.pro_api(TUSHARE_TOKEN)


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "wj_backtest_cache"
RESULTS = ROOT / "wj_backtest_results"


@dataclass
class Config:
    data_start: str = "20240601"
    backtest_start: str = "20250102"
    end: str = "20260831"
    round_trip_cost: float = 0.003
    max_positions: int = 10


def month_chunks(start: str, end: str) -> list[tuple[str, str, str]]:
    periods = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M")
    chunks = []
    for period in periods:
        lo = max(pd.Timestamp(start), period.start_time).strftime("%Y%m%d")
        hi = min(pd.Timestamp(end), period.end_time).strftime("%Y%m%d")
        chunks.append((period.strftime("%Y%m"), lo, hi))
    return chunks


def fetch_daily(config: Config) -> pd.DataFrame:
    CACHE.mkdir(exist_ok=True)
    cal_path = CACHE / f"calendar_{config.data_start}_{config.end}.pkl"
    if cal_path.exists():
        calendar = pd.read_pickle(cal_path)
    else:
        calendar = pro.trade_cal(
            exchange="SSE",
            start_date=config.data_start,
            end_date=config.end,
            is_open="1",
            fields="cal_date",
        ).sort_values("cal_date")
        calendar.to_pickle(cal_path)

    open_dates = set(calendar["cal_date"].astype(str))
    frames: list[pd.DataFrame] = []
    chunks = month_chunks(config.data_start, config.end)
    for idx, (month, lo, hi) in enumerate(chunks, start=1):
        path = CACHE / f"daily_{month}.pkl"
        if path.exists():
            frame = pd.read_pickle(path)
        else:
            month_dates = sorted(d for d in open_dates if lo <= d <= hi)
            daily_parts = []
            for j, trade_date in enumerate(month_dates, start=1):
                last_error = None
                for attempt in range(5):
                    try:
                        part = pro.daily(
                            trade_date=trade_date,
                            fields=(
                                "ts_code,trade_date,open,high,low,close,pre_close,"
                                "pct_chg,vol,amount"
                            ),
                        )
                        daily_parts.append(part)
                        last_error = None
                        break
                    except Exception as exc:  # transient proxy/API failure
                        last_error = exc
                        time.sleep(1.5 * (attempt + 1))
                if last_error is not None:
                    raise RuntimeError(f"daily {trade_date} failed: {last_error}")
                if j % 5 == 0 or j == len(month_dates):
                    print(
                        f"DOWNLOAD {month}: {j}/{len(month_dates)} days",
                        flush=True,
                    )
            frame = pd.concat(daily_parts, ignore_index=True)
            frame.to_pickle(path)
        frames.append(frame)
        print(f"CACHE {idx}/{len(chunks)} {month}: {len(frame):,} rows", flush=True)

    daily = pd.concat(frames, ignore_index=True)
    daily = daily.drop_duplicates(["ts_code", "trade_date"], keep="last")
    daily = daily.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    for col in ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]:
        daily[col] = pd.to_numeric(daily[col], errors="coerce").astype("float32")
    daily["trade_date"] = daily["trade_date"].astype(str)
    return daily


def fetch_basic() -> pd.DataFrame:
    path = CACHE / "stock_basic_all.pkl"
    if path.exists():
        return pd.read_pickle(path)
    parts = []
    for status in ["L", "D", "P"]:
        try:
            frame = pro.stock_basic(
                exchange="",
                list_status=status,
                fields="ts_code,name,industry,market,list_date,delist_date",
            )
            parts.append(frame)
        except Exception:
            continue
    basic = pd.concat(parts, ignore_index=True).drop_duplicates("ts_code", keep="first")
    basic.to_pickle(path)
    return basic


def limit_threshold(code: str) -> float:
    number = code.split(".")[0]
    if code.endswith(".BJ"):
        return 29.5
    if number.startswith(("300", "301", "688", "689")):
        return 19.5
    return 9.5


def consecutive_true(values: np.ndarray) -> np.ndarray:
    result = np.zeros(len(values), dtype=np.int16)
    run = 0
    for i, value in enumerate(values):
        run = run + 1 if bool(value) else 0
        result[i] = run
    return result


def build_signals(
    daily: pd.DataFrame, basic: pd.DataFrame, config: Config
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame], pd.Series]:
    meta = basic.set_index("ts_code")
    price_data: dict[str, pd.DataFrame] = {}
    leaders: list[dict] = []
    b3_ready: list[dict] = []
    trend: list[dict] = []

    market_daily = (
        daily[daily["trade_date"] >= config.backtest_start]
        .groupby("trade_date", observed=True)["pct_chg"]
        .mean()
        .div(100.0)
        .sort_index()
    )

    grouped = daily.groupby("ts_code", sort=False, observed=True)
    total_codes = grouped.ngroups
    for counter, (code, raw) in enumerate(grouped, start=1):
        if counter % 500 == 0 or counter == total_codes:
            print(f"FEATURES {counter}/{total_codes} codes", flush=True)
        if len(raw) < 130 or code not in meta.index:
            continue
        row_meta = meta.loc[code]
        name = str(row_meta.get("name") or "")
        industry = str(row_meta.get("industry") or "")
        list_date = str(row_meta.get("list_date") or "19000101")
        if "ST" in name.upper() or not industry or industry == "nan":
            continue

        g = raw.sort_values("trade_date").copy().reset_index(drop=True)
        ret_factor = (1.0 + g["pct_chg"].fillna(0).astype(float) / 100.0).cumprod()
        close_raw = g["close"].astype(float).replace(0, np.nan)
        g["adj_close"] = ret_factor
        g["adj_open"] = ret_factor * g["open"].astype(float) / close_raw
        g["adj_high"] = ret_factor * g["high"].astype(float) / close_raw
        g["adj_low"] = ret_factor * g["low"].astype(float) / close_raw

        c = g["adj_close"]
        amount = g["amount"].astype(float)
        vol = g["vol"].astype(float)
        for window in [5, 20, 60, 120]:
            g[f"ma{window}"] = c.rolling(window, min_periods=window).mean()
        g["prev_high120"] = c.shift(1).rolling(120, min_periods=80).max()
        g["prev_low120"] = c.shift(1).rolling(120, min_periods=80).min()
        g["prev_high20"] = c.shift(1).rolling(20, min_periods=15).max()
        g["prev_low20"] = c.shift(1).rolling(20, min_periods=15).min()
        g["ret10"] = c / c.shift(10) - 1.0
        # A leader that has already broken down should not continue to trigger
        # follower entries. Use only information available by that session close.
        g["leader_peak10"] = c.rolling(10, min_periods=10).max()
        g["leader_drawdown10"] = c / g["leader_peak10"] - 1.0
        g["ret20_pre"] = c.shift(1) / c.shift(21) - 1.0
        g["vol_ratio"] = vol / vol.shift(1).rolling(5, min_periods=5).mean()
        g["amount20"] = amount.shift(1).rolling(20, min_periods=15).mean()
        g["prior3_amount_max"] = amount.shift(1).rolling(3, min_periods=3).max()
        g["range120"] = g["prev_high120"] / g["prev_low120"] - 1.0
        g["range20"] = g["prev_high20"] / g["prev_low20"] - 1.0
        g["position120"] = (
            (c - g["prev_low120"])
            / (g["prev_high120"] - g["prev_low120"]).replace(0, np.nan)
        )
        threshold = limit_threshold(code)
        g["limit_up"] = g["pct_chg"].astype(float) >= threshold
        if "up_limit" in g.columns:
            actual_up = pd.to_numeric(g["up_limit"], errors="coerce")
            has_actual_limit = actual_up.notna() & (actual_up > 0)
            g.loc[has_actual_limit, "limit_up"] = (
                g.loc[has_actual_limit, "close"].astype(float)
                >= actual_up.loc[has_actual_limit].astype(float) - 0.005
            )
        g["limit_streak"] = consecutive_true(g["limit_up"].fillna(False).to_numpy())
        prior_qualified = (g["ret10"].shift(1) >= 0.50) | (g["limit_streak"].shift(1) >= 6)
        high_open_fade = (
            (g["ret10"] >= 0.50)
            & (g["open"].astype(float) > g["pre_close"].astype(float) * 1.01)
            & (g["close"].astype(float) < g["open"].astype(float))
        )
        g["leader_break"] = (
            prior_qualified & g["limit_up"].shift(1).fillna(False) & ~g["limit_up"]
        ) | high_open_fade

        # Point-in-time eligibility. A 60-trading-day post-listing buffer reduces IPO noise.
        g["listed"] = g["trade_date"].astype(str) >= (
            pd.Timestamp(list_date) + pd.offsets.BDay(60)
        ).strftime("%Y%m%d")
        usable = (
            (g["trade_date"] >= config.backtest_start)
            & g["listed"]
            & (g["amount20"] >= 50_000)  # Tushare amount is thousand RMB.
        )

        for i in g.index[usable & g["leader_break"]]:
            leaders.append(
                {
                    "signal_date": g.at[i, "trade_date"],
                    "industry": industry,
                    "leader_code": code,
                    "leader_name": name,
                    "leader_ret10": float(g.at[i, "ret10"]),
                    "leader_drawdown10": float(g.at[i, "leader_drawdown10"]),
                    "leader_close_below_ma5": bool(g.at[i, "adj_close"] < g.at[i, "ma5"]),
                }
            )

        horizontal = g["range120"] <= 0.20
        oversold = (c / g["prev_high120"] <= 0.70) & (g["range20"] <= 0.20)
        b3_mask = (
            usable
            & (horizontal | oversold)
            & (g["vol_ratio"] >= 1.50)
            & (g["ret20_pre"] <= 0.20)
            & (g["pct_chg"].astype(float) <= 2.0)
            & (c <= g["prev_high120"] * 1.02)
        )
        for i in g.index[b3_mask]:
            preference_score = (
                (2.0 if float(g.at[i, "close"]) < 10 else 0.0)
                + (2.0 if float(g.at[i, "prior3_amount_max"]) >= 500_000 else 0.0)
                + min(float(g.at[i, "vol_ratio"]), 4.0)
                - max(float(g.at[i, "ret20_pre"]), 0.0) * 3.0
            )
            b3_ready.append(
                {
                    "signal_date": g.at[i, "trade_date"],
                    "industry": industry,
                    "code": code,
                    "name": name,
                    "score": preference_score,
                    "close": float(g.at[i, "close"]),
                    "vol_ratio": float(g.at[i, "vol_ratio"]),
                    "ret20_pre": float(g.at[i, "ret20_pre"]),
                    "shape": "横盘" if bool(horizontal.iat[i]) else "超跌",
                }
            )

        slopes_up = (
            (g["ma20"] > g["ma20"].shift(20))
            & (g["ma60"] > g["ma60"].shift(20))
            & (g["ma120"] > g["ma120"].shift(20))
        )
        curve_ok = (
            (c >= g["ma20"])
            & (g["ma20"] >= g["ma60"])
            & (g["ma60"] >= g["ma120"])
        )
        breakout = c > g["prev_high120"] * 1.001
        first_breakout = breakout & ~breakout.shift(1).fillna(False)
        trend_mask = (
            usable
            & first_breakout
            & curve_ok
            & slopes_up
            & (g["vol_ratio"] >= 1.50)
            & (g["pct_chg"].astype(float) < 9.5)
            & (g["close"].astype(float) / g["high"].astype(float) >= 0.97)
        )
        for i in g.index[trend_mask]:
            trend.append(
                {
                    "signal_date": g.at[i, "trade_date"],
                    "code": code,
                    "name": name,
                    "industry": industry,
                    "score": min(float(g.at[i, "vol_ratio"]), 5.0)
                    + float(g.at[i, "ret10"]),
                    "breakout_level_adj": float(g.at[i, "prev_high120"]),
                    "vol_ratio": float(g.at[i, "vol_ratio"]),
                }
            )

        keep_cols = [
            "trade_date", "open", "high", "low", "close", "pre_close", "pct_chg",
            "adj_open", "adj_high", "adj_low", "adj_close", "ma5", "ma20",
        ]
        price_data[code] = g[keep_cols].set_index("trade_date")

    leader_df = pd.DataFrame(leaders)
    b3_df = pd.DataFrame(b3_ready)
    if leader_df.empty or b3_df.empty:
        b3_signals = pd.DataFrame(columns=list(b3_df.columns) + ["leader_code", "leader_name"])
    else:
        b3_signals = b3_df.merge(
            leader_df,
            on=["signal_date", "industry"],
            how="inner",
        )
        # Leader exhaustion filter: reject leaders more than 15% below their
        # 10-session closing high, or closing below MA5. This is evaluated on
        # signal date, before the follower's next-session entry.
        b3_signals = b3_signals[
            (b3_signals["leader_drawdown10"] >= -0.15)
            & ~b3_signals["leader_close_below_ma5"]
        ]
        # Recheck the leader at the follower's planned next-session entry.
        # Skip if the leader gaps down 5% or opens below the prior-session MA5.
        entry_checks = []
        for _, candidate in b3_signals.iterrows():
            leader_frame = price_data.get(str(candidate["leader_code"]))
            signal_date = str(candidate["signal_date"])
            entry_date = (
                next_trade_date(leader_frame, signal_date)
                if leader_frame is not None
                else None
            )
            if entry_date is None or signal_date not in leader_frame.index:
                entry_checks.append((np.nan, False, False))
                continue
            prior = leader_frame.loc[signal_date]
            entry_row = leader_frame.loc[entry_date]
            open_px = float(entry_row["adj_open"])
            prior_close = float(prior["adj_close"])
            prior_ma5 = float(prior["ma5"])
            gap_return = open_px / prior_close - 1.0
            entry_checks.append(
                (
                    gap_return,
                    bool(np.isfinite(prior_ma5) and open_px < prior_ma5),
                    bool(gap_return <= -0.05),
                )
            )
        b3_signals = b3_signals.copy()
        entry_audit = pd.DataFrame(
            entry_checks,
            index=b3_signals.index,
            columns=[
                "leader_entry_gap",
                "leader_entry_below_ma5",
                "leader_entry_gap_down",
            ],
        )
        b3_signals = b3_signals.join(entry_audit)
        b3_signals = b3_signals[
            ~b3_signals["leader_entry_below_ma5"]
            & ~b3_signals["leader_entry_gap_down"]
        ]
        b3_signals = b3_signals[b3_signals["code"] != b3_signals["leader_code"]]
        b3_signals = (
            b3_signals.sort_values(["signal_date", "score"], ascending=[True, False])
            .drop_duplicates(["signal_date", "code"])
            .groupby("signal_date", group_keys=False)
            .head(5)
            .reset_index(drop=True)
        )
    trend_signals = pd.DataFrame(trend).sort_values(
        ["signal_date", "score"], ascending=[True, False]
    ) if trend else pd.DataFrame()
    return b3_signals, trend_signals, price_data, market_daily


def next_trade_date(frame: pd.DataFrame, signal_date: str) -> str | None:
    dates = frame.index.to_numpy(dtype=str)
    pos = np.searchsorted(dates, signal_date, side="right")
    return str(dates[pos]) if pos < len(dates) else None


def simulate_short_trade(
    signal: pd.Series,
    frame: pd.DataFrame,
    config: Config,
) -> dict | None:
    entry_date = next_trade_date(frame, str(signal["signal_date"]))
    if entry_date is None:
        return None
    entry_loc = frame.index.get_loc(entry_date)
    entry_row = frame.iloc[entry_loc]
    entry = float(entry_row["adj_open"])
    entry_raw = float(entry_row["open"])
    signal_close = float(frame.loc[str(signal["signal_date"]), "adj_close"])
    if not np.isfinite(entry) or entry <= 0 or entry / signal_close - 1 > 0.07:
        return None

    stop = entry * 0.95
    remaining = 1.0
    cash_factor = 0.0
    peak = entry
    path: dict[str, float] = {}
    reason = "样本结束"
    exit_date = str(frame.index[-1])
    exit_price = float(frame.iloc[-1]["adj_close"])
    end_loc = min(entry_loc + 6, len(frame) - 1)
    pending_exit = False

    for loc in range(entry_loc, end_loc + 1):
        date = str(frame.index[loc])
        row = frame.iloc[loc]
        day_open, day_high, day_low, day_close = map(
            float, [row["adj_open"], row["adj_high"], row["adj_low"], row["adj_close"]]
        )
        if pending_exit:
            exit_price = day_open
            exit_date = date
            reason = "时间/MA5退出"
            cash_factor += remaining * exit_price / entry
            remaining = 0.0
        elif remaining > 0:
            if day_low <= stop:
                exit_price = stop if day_open > stop else day_open
                exit_date = date
                reason = "-5%硬止损"
                cash_factor += remaining * exit_price / entry
                remaining = 0.0
            else:
                peak = max(peak, day_high)
                trail = peak * 0.95
                # OHLC bars do not reveal whether the high came before the low;
                # if both imply a trail touch, conservatively assume it did.
                if day_open <= trail or day_low <= trail:
                    exit_price = day_open if day_open <= trail else trail
                    exit_date = date
                    reason = "买入后最高价回撤5%"
                    cash_factor += remaining * exit_price / entry
                    remaining = 0.0

        if remaining > 0:
            path[date] = cash_factor + remaining * day_close / entry - config.round_trip_cost / 2
            held = loc - entry_loc + 1
            if held >= 3 and day_close / entry - 1 < 0.02:
                pending_exit = True
            if np.isfinite(row["ma5"]) and float(row["adj_close"]) < float(row["ma5"]):
                pending_exit = True
            if loc == end_loc:
                exit_price = day_close
                exit_date = date
                reason = "7日上限"
                cash_factor += remaining * exit_price / entry
                remaining = 0.0
        if remaining <= 0:
            final_factor = cash_factor - config.round_trip_cost
            path[date] = final_factor
            break

    if remaining > 0:
        cash_factor += remaining * exit_price / entry
        final_factor = cash_factor - config.round_trip_cost
        path[exit_date] = final_factor
    else:
        final_factor = cash_factor - config.round_trip_cost
    return {
        **signal.to_dict(),
        "entry_date": entry_date,
        "entry_price": entry,
        "entry_price_raw": entry_raw,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "holding_days": list(frame.index).index(exit_date) - entry_loc + 1,
        "net_return": final_factor - 1.0,
        "exit_reason": reason,
        "path": path,
    }


def simulate_trend_trade(
    signal: pd.Series,
    frame: pd.DataFrame,
    config: Config,
) -> dict | None:
    entry_date = next_trade_date(frame, str(signal["signal_date"]))
    if entry_date is None:
        return None
    entry_loc = frame.index.get_loc(entry_date)
    entry = float(frame.iloc[entry_loc]["adj_open"])
    entry_raw = float(frame.iloc[entry_loc]["open"])
    signal_close = float(frame.loc[str(signal["signal_date"]), "adj_close"])
    if not np.isfinite(entry) or entry <= 0 or entry / signal_close - 1 > 0.07:
        return None
    stop = entry * 0.92
    breakout = float(signal.get("breakout_level_adj", np.nan))
    below_count = 0
    pending_reason: str | None = None
    path: dict[str, float] = {}
    exit_date = str(frame.index[-1])
    exit_price = float(frame.iloc[-1]["adj_close"])
    reason = "样本结束持有"

    for loc in range(entry_loc, len(frame)):
        date = str(frame.index[loc])
        row = frame.iloc[loc]
        day_open, day_low, day_close = map(
            float, [row["adj_open"], row["adj_low"], row["adj_close"]]
        )
        if pending_reason is not None:
            exit_date, exit_price, reason = date, day_open, pending_reason
            path[date] = exit_price / entry - config.round_trip_cost
            break
        if day_low <= stop:
            exit_date = date
            exit_price = stop if day_open > stop else day_open
            reason = "-8%初始止损"
            path[date] = exit_price / entry - config.round_trip_cost
            break
        path[date] = day_close / entry - config.round_trip_cost / 2
        ma_break = np.isfinite(row["ma20"]) and float(row["adj_close"]) < float(row["ma20"])
        platform_break = np.isfinite(breakout) and float(row["adj_close"]) < breakout
        below_count = below_count + 1 if (ma_break or platform_break) else 0
        if below_count >= 2:
            pending_reason = "连续2日跌破20日线/平台"
    else:
        path[exit_date] = exit_price / entry - config.round_trip_cost

    final_factor = path[exit_date]
    return {
        **signal.to_dict(),
        "entry_date": entry_date,
        "entry_price": entry,
        "entry_price_raw": entry_raw,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "holding_days": list(frame.index).index(exit_date) - entry_loc + 1,
        "net_return": final_factor - 1.0,
        "exit_reason": reason,
        "path": path,
    }


def run_trade_simulations(
    signals: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
    config: Config,
    branch: str,
) -> list[dict]:
    if signals.empty:
        return []
    trades: list[dict] = []
    last_exit: dict[str, str] = {}
    simulator = simulate_short_trade if branch == "b3" else simulate_trend_trade
    for _, signal in signals.sort_values(["signal_date", "score"], ascending=[True, False]).iterrows():
        code = str(signal["code"])
        if code not in price_data:
            continue
        if code in last_exit and str(signal["signal_date"]) <= last_exit[code]:
            continue
        trade = simulator(signal, price_data[code], config)
        if trade is not None:
            trades.append(trade)
            last_exit[code] = str(trade["exit_date"])
    return trades


def add_benchmark_return(trades: list[dict], market_daily: pd.Series) -> None:
    for trade in trades:
        series = market_daily.loc[
            (market_daily.index >= trade["entry_date"])
            & (market_daily.index <= trade["exit_date"])
        ]
        benchmark = float((1.0 + series).prod() - 1.0) if len(series) else 0.0
        trade["benchmark_return"] = benchmark
        trade["excess_return"] = trade["net_return"] - benchmark


def trade_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    r = pd.Series([trade["net_return"] for trade in trades], dtype=float)
    excess = pd.Series([trade.get("excess_return", np.nan) for trade in trades], dtype=float)
    wins = r[r > 0]
    losses = r[r <= 0]
    return {
        "trades": int(len(r)),
        "win_rate": float((r > 0).mean()),
        "mean_return": float(r.mean()),
        "median_return": float(r.median()),
        "mean_excess": float(excess.mean()),
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() < 0 else None,
        "best": float(r.max()),
        "worst": float(r.min()),
        "avg_holding_days": float(np.mean([t["holding_days"] for t in trades])),
        "open_at_end": int(sum(t["exit_reason"] == "样本结束持有" for t in trades)),
    }


def portfolio_curve(
    trades: list[dict], market_daily: pd.Series, config: Config
) -> tuple[pd.DataFrame, dict, list[dict]]:
    if not trades:
        return pd.DataFrame(), {"trades": 0}, []
    dates = list(market_daily.index)
    entries: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        entries[trade["entry_date"]].append(trade)
    cash = 1.0
    active: list[dict] = []
    accepted: list[dict] = []
    rows = []
    for date in dates:
        equity_before = cash + sum(
            pos["allocation"] * pos["trade"]["path"].get(
                pos["last_date"], pos["last_factor"]
            )
            for pos in active
        )
        occupied_codes = {pos["trade"]["code"] for pos in active}
        for trade in sorted(entries.get(date, []), key=lambda x: x.get("score", 0), reverse=True):
            if len(active) >= config.max_positions or trade["code"] in occupied_codes:
                continue
            allocation = min(equity_before / config.max_positions, cash)
            if allocation <= 1e-9:
                break
            cash -= allocation
            active.append(
                {
                    "trade": trade,
                    "allocation": allocation,
                    "last_factor": 1.0,
                    "last_date": date,
                }
            )
            accepted.append(trade)
            occupied_codes.add(trade["code"])

        still_active = []
        for pos in active:
            trade = pos["trade"]
            if date in trade["path"]:
                pos["last_factor"] = trade["path"][date]
                pos["last_date"] = date
            if date >= trade["exit_date"]:
                cash += pos["allocation"] * pos["last_factor"]
            else:
                still_active.append(pos)
        active = still_active
        equity = cash + sum(pos["allocation"] * pos["last_factor"] for pos in active)
        rows.append({"trade_date": date, "equity": equity, "active_positions": len(active)})

    curve = pd.DataFrame(rows).set_index("trade_date")
    curve["daily_return"] = curve["equity"].pct_change().fillna(0.0)
    curve["benchmark_equity"] = (1.0 + market_daily.reindex(curve.index).fillna(0.0)).cumprod()
    drawdown = curve["equity"] / curve["equity"].cummax() - 1.0
    daily = curve["daily_return"]
    years = max(len(curve) / 244.0, 1 / 244.0)
    total = float(curve["equity"].iloc[-1] - 1.0)
    benchmark_total = float(curve["benchmark_equity"].iloc[-1] - 1.0)
    annual = float(curve["equity"].iloc[-1] ** (1.0 / years) - 1.0)
    vol = float(daily.std(ddof=0) * math.sqrt(244))
    metrics = {
        "accepted_trades": len(accepted),
        "total_return": total,
        "annualized_return": annual,
        "max_drawdown": float(drawdown.min()),
        "annualized_volatility": vol,
        "sharpe_zero_rf": float(annual / vol) if vol > 0 else None,
        "benchmark_total_return": benchmark_total,
        "excess_total_return": total - benchmark_total,
        "average_position_count": float(curve["active_positions"].mean()),
        "max_position_count": int(curve["active_positions"].max()),
    }
    return curve, metrics, accepted


def historical_snapshot_signals() -> pd.DataFrame:
    rows = []
    pattern = re.compile(r"screen_202608.*_output\.json$")
    for path in sorted(ROOT.glob("screen_202608*_output.json")):
        if not pattern.search(path.name) or "postmortem" in path.name:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        signal_date = str(payload.get("trade_date"))
        for row in payload.get("curve_candidates", []):
            if row.get("long_curve") and row.get("all_long_slopes_up") and not row.get("error"):
                rows.append(
                    {
                        "signal_date": signal_date,
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "industry": row.get("industry"),
                        "score": float(row.get("vol5_ratio") or 0),
                        "breakout_level_adj": np.nan,
                        "source_file": path.name,
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(["signal_date", "code"])


def snapshot_forward_audit(
    signals: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
    market_daily: pd.Series,
    config: Config,
) -> tuple[pd.DataFrame, dict]:
    rows = []
    for _, signal in signals.iterrows():
        code = str(signal["code"])
        if code not in price_data:
            continue
        frame = price_data[code]
        entry_date = next_trade_date(frame, str(signal["signal_date"]))
        if entry_date is None:
            continue
        entry_loc = frame.index.get_loc(entry_date)
        entry = float(frame.iloc[entry_loc]["adj_open"])
        item = {**signal.to_dict(), "entry_date": entry_date}
        for horizon in [1, 3, 5]:
            exit_loc = entry_loc + horizon - 1
            if exit_loc >= len(frame):
                item[f"ret_{horizon}d"] = np.nan
                item[f"excess_{horizon}d"] = np.nan
                continue
            exit_date = str(frame.index[exit_loc])
            stock_return = (
                float(frame.iloc[exit_loc]["adj_close"]) / entry
                - 1.0
                - config.round_trip_cost
            )
            bench = market_daily.loc[
                (market_daily.index >= entry_date) & (market_daily.index <= exit_date)
            ]
            benchmark_return = float((1.0 + bench).prod() - 1.0) if len(bench) else 0.0
            item[f"ret_{horizon}d"] = stock_return
            item[f"excess_{horizon}d"] = stock_return - benchmark_return
        last_loc = min(entry_loc + 4, len(frame) - 1)
        window = frame.iloc[entry_loc : last_loc + 1]
        item["mfe_5d"] = float(window["adj_high"].max() / entry - 1.0)
        item["mae_5d"] = float(window["adj_low"].min() / entry - 1.0)
        rows.append(item)
    audit = pd.DataFrame(rows)
    metrics = {}
    for horizon in [1, 3, 5]:
        column = f"ret_{horizon}d"
        excess_column = f"excess_{horizon}d"
        sample = audit[column].dropna() if column in audit else pd.Series(dtype=float)
        metrics[f"{horizon}d"] = {
            "count": int(len(sample)),
            "mean_return": float(sample.mean()) if len(sample) else None,
            "median_return": float(sample.median()) if len(sample) else None,
            "win_rate": float((sample > 0).mean()) if len(sample) else None,
            "mean_excess": float(audit.loc[sample.index, excess_column].mean()) if len(sample) else None,
        }
    return audit, metrics


def serializable_trades(trades: list[dict]) -> list[dict]:
    result = []
    for trade in trades:
        item = {k: v for k, v in trade.items() if k != "path"}
        for key, value in list(item.items()):
            if isinstance(value, (np.integer,)):
                item[key] = int(value)
            elif isinstance(value, (np.floating,)):
                item[key] = None if not np.isfinite(value) else float(value)
        result.append(item)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-start", default="20240601")
    parser.add_argument("--backtest-start", default="20250102")
    parser.add_argument("--end", default="20260831")
    args = parser.parse_args()
    config = Config(args.data_start, args.backtest_start, args.end)
    RESULTS.mkdir(exist_ok=True)

    daily = fetch_daily(config)
    basic = fetch_basic()
    b3_signals, trend_signals, price_data, market_daily = build_signals(daily, basic, config)

    b3_trades = run_trade_simulations(b3_signals, price_data, config, "b3")
    trend_trades = run_trade_simulations(trend_signals, price_data, config, "trend")
    add_benchmark_return(b3_trades, market_daily)
    add_benchmark_return(trend_trades, market_daily)
    b3_curve, b3_portfolio, b3_accepted = portfolio_curve(b3_trades, market_daily, config)
    trend_curve, trend_portfolio, trend_accepted = portfolio_curve(
        trend_trades, market_daily, config
    )

    snapshot_signals = historical_snapshot_signals()
    snapshot_trades = run_trade_simulations(snapshot_signals, price_data, config, "trend")
    add_benchmark_return(snapshot_trades, market_daily)
    snapshot_forward, snapshot_forward_metrics = snapshot_forward_audit(
        snapshot_signals, price_data, market_daily, config
    )

    summary = {
        "config": config.__dict__,
        "methodology": {
            "b3": "B.1/B.2 leader break + same-industry proxy + B.3 bottom/volume gate; next-open entry",
            "trend": "C.3/C.4 technical execution proxy only; no historical fundamental/theme look-ahead",
            "cost": config.round_trip_cost,
            "benchmark": "daily-rebalanced all-A equal-weight return",
        },
        "data": {
            "rows": len(daily),
            "codes": int(daily["ts_code"].nunique()),
            "first_date": str(daily["trade_date"].min()),
            "last_date": str(daily["trade_date"].max()),
        },
        "b3": {
            "signals": len(b3_signals),
            "trade_metrics": trade_metrics(b3_trades),
            "portfolio_metrics": b3_portfolio,
        },
        "trend": {
            "signals": len(trend_signals),
            "trade_metrics": trade_metrics(trend_trades),
            "portfolio_metrics": trend_portfolio,
        },
        "historical_snapshot_audit": {
            "signals": len(snapshot_signals),
            "trade_metrics": trade_metrics(snapshot_trades),
            "forward_metrics": snapshot_forward_metrics,
        },
    }

    (RESULTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(serializable_trades(b3_trades)).to_csv(
        RESULTS / "b3_trades.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(serializable_trades(trend_trades)).to_csv(
        RESULTS / "trend_trades.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(serializable_trades(snapshot_trades)).to_csv(
        RESULTS / "snapshot_audit_trades.csv", index=False, encoding="utf-8-sig"
    )
    snapshot_forward.to_csv(
        RESULTS / "snapshot_forward_returns.csv", index=False, encoding="utf-8-sig"
    )
    if not b3_curve.empty:
        b3_curve.to_csv(RESULTS / "b3_equity_curve.csv", encoding="utf-8-sig")
    if not trend_curve.empty:
        trend_curve.to_csv(RESULTS / "trend_equity_curve.csv", encoding="utf-8-sig")
    b3_signals.to_csv(RESULTS / "b3_signals.csv", index=False, encoding="utf-8-sig")
    trend_signals.to_csv(RESULTS / "trend_signals.csv", index=False, encoding="utf-8-sig")
    print("RESULT")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
