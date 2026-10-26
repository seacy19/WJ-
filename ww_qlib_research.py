"""WW price-factor proxy research using Qlib + purged walk-forward validation.

This does not claim to backtest WW's human/PIT fundamental or sector-mainline legs.
It only tests cross-sectional leader identification at causal technical breakouts.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import warnings
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import optuna
import qlib
from qlib.data.dataset import DatasetH
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.loader import StaticDataLoader


class _TrialRecorder:
    """Qlib's built-in LightGBM logs iteration metrics through R; Optuna records trials here."""
    def start(self, **kwargs):
        return nullcontext()

    def log_params(self, **kwargs):
        return None

    def log_metrics(self, **kwargs):
        return None

    def save_objects(self, **kwargs):
        return None


_workflow_stub = ModuleType("qlib.workflow")
_workflow_stub.R = _TrialRecorder()
sys.modules.setdefault("qlib.workflow", _workflow_stub)
from qlib.contrib.model.gbdt import LGBModel

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "wj_backtest_cache"
OUT = ROOT / "ww_research_results"
OUT.mkdir(parents=True, exist_ok=True)
START = "20240601"
END = "20260831"
TRAIN_CUTOFF = "20250630"
VALID_START = "20250701"
VALID_END = "20251231"
TEST_START = "20260101"
TEST_LAST_SIGNAL = "20260601"  # 60 trading days remain for forward validation.
ROUND_TRIP_COST = 0.003
MAX_POSITIONS = 10
SEED = 619

FEATURES = [
    "mom5", "mom20", "mom60", "mom120", "ma20_gap", "ma60_gap", "ma120_gap",
    "ma20_60", "ma60_120", "slope20", "slope60", "slope120", "dd60", "dd120",
    "vol_ratio", "amount_log", "vol20", "vol60", "range20", "range60",
    "close_location", "gap_high20", "gap_high60", "gap_high120", "rs20", "rs60",
]


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(CACHE.glob("daily_*.pkl"))
    if not files:
        raise FileNotFoundError(f"No monthly daily_*.pkl files under {CACHE}")
    chunks = [pd.read_pickle(p) for p in files]
    daily = pd.concat(chunks, ignore_index=True).drop_duplicates(["ts_code", "trade_date"])
    daily = daily.sort_values(["ts_code", "trade_date"], kind="mergesort")
    for c in ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]:
        daily[c] = pd.to_numeric(daily[c], errors="coerce").astype("float32")
    basic = pd.read_pickle(CACHE / "stock_basic_all.pkl")
    basic = basic.drop_duplicates("ts_code").set_index("ts_code")
    log(f"loaded {len(daily):,} bars, {daily.ts_code.nunique():,} instruments")
    return daily, basic


def build_candidates(daily: pd.DataFrame, basic: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Broad market equal-weight return is used only as a relative-strength feature.
    mkt = daily.groupby("trade_date", observed=True)["pct_chg"].mean().sort_index() / 100.0
    mkt_growth = (1.0 + mkt).cumprod()
    mkt_r20 = mkt_growth / mkt_growth.shift(20) - 1.0
    mkt_r60 = mkt_growth / mkt_growth.shift(60) - 1.0
    records: list[pd.DataFrame] = []
    bar_parts: list[pd.DataFrame] = []
    grouped = daily.groupby("ts_code", sort=False, observed=True)
    for n, (code, raw) in enumerate(grouped, 1):
        if n % 1000 == 0:
            log(f"feature build {n:,}/{grouped.ngroups:,}")
        if code not in basic.index or len(raw) < 220:
            continue
        meta = basic.loc[code]
        name = str(meta.get("name", ""))
        industry = str(meta.get("industry", ""))
        if "ST" in name.upper() or not industry or industry == "nan":
            continue
        g = raw.reset_index(drop=True).copy()
        date = g["trade_date"].astype(str)
        c0 = g["close"].astype(float).replace(0, np.nan)
        growth = (1.0 + g["pct_chg"].astype(float).fillna(0.0) / 100).cumprod()
        c = growth
        o = growth * g["open"].astype(float) / c0
        h = growth * g["high"].astype(float) / c0
        l = growth * g["low"].astype(float) / c0
        vol = g["vol"].astype(float)
        amount = g["amount"].astype(float)
        ma20, ma60, ma120 = (c.rolling(w, min_periods=w).mean() for w in (20, 60, 120))
        prev_hi20 = c.shift(1).rolling(20, min_periods=18).max()
        prev_hi60 = c.shift(1).rolling(60, min_periods=50).max()
        prev_hi120 = c.shift(1).rolling(120, min_periods=100).max()
        prev_hi180 = c.shift(1).rolling(180, min_periods=150).max()
        prev_hi20raw = h.shift(1).rolling(20, min_periods=18).max()
        prev_lo20raw = l.shift(1).rolling(20, min_periods=18).min()
        vol_base = vol.shift(1).rolling(20, min_periods=15).mean()
        vol_ratio = vol / vol_base.replace(0, np.nan)
        amount20 = amount.shift(1).rolling(20, min_periods=15).mean()
        rv20 = (g["pct_chg"].astype(float) / 100).rolling(20, min_periods=18).std() * math.sqrt(244)
        rv60 = (g["pct_chg"].astype(float) / 100).rolling(60, min_periods=50).std() * math.sqrt(244)
        ret = lambda w: c / c.shift(w) - 1.0
        list_date = str(meta.get("list_date", "19000101"))
        listed_date = (pd.Timestamp(list_date) + pd.offsets.BDay(60)).strftime("%Y%m%d")
        eligible = (date >= listed_date) & (date >= START) & (date <= END) & (amount20 >= 50_000)
        rising = (ma20 > ma20.shift(20)) & (ma60 > ma60.shift(20)) & (ma120 > ma120.shift(20))
        aligned = (c >= ma20) & (ma20 >= ma60) & (ma60 >= ma120)
        base_gate = (
            eligible & rising & aligned & (g["pct_chg"].astype(float) < 9.5)
            & (c / h.replace(0, np.nan) >= 0.97) & (vol_ratio >= 0.8)
        )
        high_windows = {60: prev_hi60, 90: c.shift(1).rolling(90, min_periods=75).max(),
                        120: prev_hi120, 180: prev_hi180}
        breaks = {}
        for w, level in high_windows.items():
            above = c > level * 1.001
            breaks[w] = above & ~above.shift(1).fillna(False)
        candidate_any = pd.Series(False, index=g.index)
        for mask in breaks.values():
            candidate_any |= mask.fillna(False)
        mask = base_gate & candidate_any
        if not mask.any():
            continue
        locs = np.flatnonzero(mask.to_numpy())
        r20, r60 = ret(20), ret(60)
        mr20 = date.map(mkt_r20).astype(float)
        mr60 = date.map(mkt_r60).astype(float)
        high120 = prev_hi120
        prev_ma20 = ma20
        # Features are known at signal-date close. Labels enter at next open.
        f = pd.DataFrame({
            "datetime": date.iloc[locs].values,
            "instrument": code,
            "code": code,
            "name": name,
            "industry": industry,
            "open": o.iloc[locs].values,
            "high": h.iloc[locs].values,
            "low": l.iloc[locs].values,
            "close": c.iloc[locs].values,
            "ma20": ma20.iloc[locs].values,
            "breakout_level": high120.iloc[locs].values,
            "vol_ratio": vol_ratio.iloc[locs].values,
            "amount20": amount20.iloc[locs].values,
            "mom5": ret(5).iloc[locs].values,
            "mom20": r20.iloc[locs].values,
            "mom60": r60.iloc[locs].values,
            "mom120": ret(120).iloc[locs].values,
            "ma20_gap": (c / ma20 - 1).iloc[locs].values,
            "ma60_gap": (c / ma60 - 1).iloc[locs].values,
            "ma120_gap": (c / ma120 - 1).iloc[locs].values,
            "ma20_60": (ma20 / ma60 - 1).iloc[locs].values,
            "ma60_120": (ma60 / ma120 - 1).iloc[locs].values,
            "slope20": (ma20 / ma20.shift(20) - 1).iloc[locs].values,
            "slope60": (ma60 / ma60.shift(20) - 1).iloc[locs].values,
            "slope120": (ma120 / ma120.shift(20) - 1).iloc[locs].values,
            "dd60": (c / c.shift(1).rolling(60, min_periods=50).max() - 1).iloc[locs].values,
            "dd120": (c / high120 - 1).iloc[locs].values,
            "amount_log": np.log1p(amount20.iloc[locs].clip(lower=0).values),
            "vol20": rv20.iloc[locs].values,
            "vol60": rv60.iloc[locs].values,
            "range20": (prev_hi20raw / prev_lo20raw - 1).iloc[locs].values,
            "range60": ((h.shift(1).rolling(60, min_periods=50).max()) / (l.shift(1).rolling(60, min_periods=50).min()) - 1).iloc[locs].values,
            "close_location": ((c - l) / (h - l).replace(0, np.nan)).iloc[locs].values,
            "gap_high20": (c / prev_hi20 - 1).iloc[locs].values,
            "gap_high60": (c / prev_hi60 - 1).iloc[locs].values,
            "gap_high120": (c / prev_hi120 - 1).iloc[locs].values,
            "rs20": (r20 - mr20).iloc[locs].values,
            "rs60": (r60 - mr60).iloc[locs].values,
            "signal_ret": g["pct_chg"].iloc[locs].values.astype(float) / 100,
            "signal_vol_ratio": vol_ratio.iloc[locs].values,
            "listed_date": listed_date,
        })
        for w, breakout_mask in breaks.items():
            f[f"break_{w}"] = breakout_mask.iloc[locs].astype("int8").values
        # Midline outcome: next-session open to the 60th-session close.
        f["label60"] = (c.shift(-60) / o.shift(-1) - 1).iloc[locs].values
        # C.4 trade bars include actual next-open and full future daily path.
        bar_parts.append(pd.DataFrame({
            "datetime": date.values, "instrument": code,
            "open": o.values, "high": h.values, "low": l.values,
            "close": c.values, "ma20": prev_ma20.values,
        }))
        records.append(f)
    panel = pd.concat(records, ignore_index=True).replace([np.inf, -np.inf], np.nan)
    bars = pd.concat(bar_parts, ignore_index=True)
    panel = panel.sort_values(["datetime", "instrument"], kind="mergesort").reset_index(drop=True)
    bars = bars.sort_values(["datetime", "instrument"], kind="mergesort").reset_index(drop=True)
    panel.to_parquet(OUT / "candidate_panel.parquet", index=False)
    bars.to_parquet(OUT / "candidate_bars.parquet", index=False)
    log(f"candidate rows {len(panel):,}; price rows {len(bars):,}")
    return panel, bars


def qlib_dataset(panel: pd.DataFrame, train_end: str, valid_start: str, valid_end: str) -> DatasetH:
    data = panel.dropna(subset=FEATURES + ["label60"]).copy()
    # Percentile ranks are cross-sectional and only use the same day's observable candidate set.
    ranked = data.groupby("datetime", sort=False)[FEATURES].rank(pct=True).astype("float32")
    ranked.columns = pd.MultiIndex.from_product([["feature"], FEATURES])
    label = data[["label60"]].astype("float32")
    label.columns = pd.MultiIndex.from_product([["label"], ["LABEL60"]])
    qdf = pd.concat([ranked, label], axis=1)
    qdf.index = pd.MultiIndex.from_arrays(
        [pd.to_datetime(data["datetime"]), data["instrument"]], names=["datetime", "instrument"]
    )
    qdf = qdf.sort_index()
    # Purge boundary labels: labels must mature before the next segment begins.
    trading_dates = sorted(data["datetime"].unique())
    train_pos = max(0, np.searchsorted(trading_dates, train_end, side="right") - 61)
    purged_train_end = trading_dates[train_pos]
    handler = DataHandlerLP(data_loader=StaticDataLoader(qdf), start_time=START, end_time=END)
    return DatasetH(handler=handler, segments={
        "train": (START, str(purged_train_end)),
        "valid": (valid_start, valid_end),
        "test": (TEST_START, END),
    })


def simulate_candidate(signal: pd.Series, bar_groups: dict[str, pd.DataFrame], stop_pct: float, max_hold: int) -> dict | None:
    code = str(signal["code"])
    frame = bar_groups.get(code)
    if frame is None:
        return None
    dates = frame["datetime"].to_numpy(dtype=str)
    i = int(np.searchsorted(dates, str(signal["datetime"]), side="right"))
    if i >= len(frame):
        return None
    entry_row = frame.iloc[i]
    entry = float(entry_row["open"])
    signal_close = float(signal["close"])
    if not np.isfinite(entry) or entry <= 0 or entry / signal_close - 1 > 0.07:
        return None
    stop = entry * (1 - stop_pct)
    breakout = float(signal["breakout_level"])
    path: dict[str, float] = {}
    below = 0
    reason = "持有上限"
    exit_date = dates[min(i + max_hold - 1, len(dates) - 1)]
    final_factor = 1.0
    end = min(i + max_hold, len(frame))
    for j in range(i, end):
        row = frame.iloc[j]
        day, day_open, lo, close = dates[j], float(row.open), float(row.low), float(row.close)
        if lo <= stop:
            # Daily bars cannot reveal intraday path; if open is below stop, use the open.
            exit_price = float(row.open) if float(row.open) < stop else stop
            final_factor = exit_price / entry - ROUND_TRIP_COST
            exit_date, reason = day, "初始止损"
            path[day] = final_factor
            break
        path[day] = close / entry - ROUND_TRIP_COST / 2
        ma_break = np.isfinite(row.ma20) and close < float(row.ma20)
        platform_break = np.isfinite(breakout) and close < breakout
        below = below + 1 if ma_break or platform_break else 0
        if below >= 2 and j + 1 < len(frame):
            out = frame.iloc[j + 1]
            exit_date = str(dates[j + 1])
            final_factor = float(out.open) / entry - ROUND_TRIP_COST
            path[exit_date] = final_factor
            reason = "连续两日跌破趋势/平台"
            break
    else:
        last = min(i + max_hold - 1, len(frame) - 1)
        exit_date = str(dates[last])
        final_factor = float(frame.iloc[last].close) / entry - ROUND_TRIP_COST
        path[exit_date] = final_factor
    return {"code": code, "signal_date": str(signal.datetime), "entry_date": str(dates[i]),
            "exit_date": exit_date, "return": final_factor - 1, "path": path,
            "score": float(signal.pred), "reason": reason}


def portfolio_backtest(predictions: pd.DataFrame, panel: pd.DataFrame, bars: pd.DataFrame,
                       topk: int, stop_pct: float, max_hold: int,
                       start: str, end: str,
                       benchmark_daily: pd.Series | None = None) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    pred = predictions.reset_index()
    if "datetime" not in pred.columns:
        pred = pred.rename(columns={pred.columns[0]: "datetime"})
    if "instrument" not in pred.columns:
        pred = pred.rename(columns={pred.columns[1]: "instrument"})
    pred = pred.rename(columns={pred.columns[-1]: "pred"})
    pred["datetime"] = pd.to_datetime(pred["datetime"]).dt.strftime("%Y%m%d")
    pred = pred[(pred.datetime >= start) & (pred.datetime <= end)]
    meta_cols = ["datetime", "instrument", "code", "close", "breakout_level"]
    pred = pred.merge(panel[meta_cols].drop_duplicates(["datetime", "instrument"]), on=["datetime", "instrument"], how="left")
    bar_groups = {code: grp.reset_index(drop=True) for code, grp in bars.groupby("instrument", sort=False)}
    trades: list[dict] = []
    active_until: dict[str, str] = {}
    # Candidate ranks refresh at each close; orders execute next open, capped at 10 concurrent names.
    for date, grp in pred.groupby("datetime", sort=True):
        active_until = {c: d for c, d in active_until.items() if d >= date}
        for _, row in grp.sort_values("pred", ascending=False).head(max(topk * 4, topk)).iterrows():
            if len(active_until) >= MAX_POSITIONS:
                break
            code = str(row.code)
            if code in active_until:
                continue
            trade = simulate_candidate(row, bar_groups, stop_pct, max_hold)
            if trade is None:
                continue
            trade["date"] = date
            trades.append(trade)
            active_until[code] = trade["exit_date"]
    # Non-overlapping daily equity mark-to-market from accepted trades.
    dates = sorted(set(bars.loc[(bars.datetime >= start) & (bars.datetime <= end), "datetime"]))
    equity = 1.0
    daily_rows = []
    by_entry: dict[str, list[dict]] = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)
    active: list[dict] = []
    cash = 1.0
    accepted = []
    for date in dates:
        before = cash + sum(p["allocation"] * p["factor"] for p in active)
        for t in by_entry.get(date, []):
            if len(active) >= MAX_POSITIONS:
                continue
            alloc = min(before / MAX_POSITIONS, cash)
            if alloc <= 1e-9:
                continue
            cash -= alloc
            active.append({"trade": t, "allocation": alloc, "factor": 1.0})
            accepted.append(t)
        survivors = []
        for p in active:
            path = p["trade"]["path"]
            if date in path:
                p["factor"] = float(path[date])
            if date >= p["trade"]["exit_date"]:
                cash += p["allocation"] * p["factor"]
            else:
                survivors.append(p)
        active = survivors
        equity = cash + sum(p["allocation"] * p["factor"] for p in active)
        daily_rows.append({"date": date, "equity": equity, "positions": len(active)})
    curve = pd.DataFrame(daily_rows)
    if curve.empty:
        return {"trades": 0}, curve, pd.DataFrame()
    curve["ret"] = curve.equity.pct_change().fillna(0)
    dd = curve.equity / curve.equity.cummax() - 1
    years = max(len(curve) / 244, 1 / 244)
    ann = float(curve.equity.iloc[-1] ** (1 / years) - 1)
    vol = float(curve.ret.std(ddof=0) * math.sqrt(244))
    accepted_df = pd.DataFrame(accepted)
    met = {"trades": len(accepted), "total_return": float(curve.equity.iloc[-1] - 1),
           "annualized_return": ann, "max_drawdown": float(dd.min()),
           "annualized_volatility": vol, "sharpe_zero_rf": ann / vol if vol else None,
           "win_rate": float((accepted_df["return"] > 0).mean()) if len(accepted_df) else None,
           "mean_trade_return": float(accepted_df["return"].mean()) if len(accepted_df) else None,
           "mean_positions": float(curve.positions.mean())}
    if benchmark_daily is not None:
        benchmark_returns = benchmark_daily.reindex(curve.date).fillna(0).to_numpy(dtype=float)
        benchmark_equity = np.cumprod(1 + benchmark_returns)
        met["benchmark_total_return"] = float(benchmark_equity[-1] - 1)
        met["excess_return_vs_benchmark"] = float(met["total_return"] - met["benchmark_total_return"])
        curve["benchmark_equity"] = benchmark_equity
    return met, curve, accepted_df


def fit_predict(panel: pd.DataFrame, params: dict, train_end: str, valid_start: str,
                valid_end: str, predict_segment: str) -> tuple[pd.Series, dict]:
    data = panel.dropna(subset=FEATURES + ["label60"])
    qdf_features = data[FEATURES].groupby(data["datetime"], sort=False).rank(pct=True).astype("float32")
    qdf_features.columns = pd.MultiIndex.from_product([["feature"], FEATURES])
    qdf_label = data[["label60"]].astype("float32")
    qdf_label.columns = pd.MultiIndex.from_product([["label"], ["LABEL60"]])
    qdf = pd.concat([qdf_features, qdf_label], axis=1)
    qdf.index = pd.MultiIndex.from_arrays([pd.to_datetime(data.datetime), data.instrument], names=["datetime", "instrument"])
    qdf = qdf.sort_index()
    td = sorted(data.datetime.unique())
    cutoff = max(0, np.searchsorted(td, train_end, side="right") - 61)
    train_end_purged = td[cutoff]
    handler = DataHandlerLP(data_loader=StaticDataLoader(qdf), start_time=START, end_time=END)
    ds = DatasetH(handler=handler, segments={
        "train": (START, str(train_end_purged)), "valid": (valid_start, valid_end),
        "test": (TEST_START, END),
    })
    model = LGBModel(loss="mse", num_boost_round=params["num_boost_round"],
                     early_stopping_rounds=50, **{k: v for k, v in params.items() if k != "num_boost_round"})
    model.fit(ds, verbose_eval=0)
    pred = model.predict(ds, predict_segment)
    return pred, {"best_iteration": int(getattr(model.model, "best_iteration", 0) or params["num_boost_round"])}


def rank_ic(pred: pd.Series, panel: pd.DataFrame) -> dict:
    p = pred.rename("pred").reset_index()
    p = p.rename(columns={p.columns[0]: "datetime", p.columns[1]: "instrument"})
    p["datetime"] = pd.to_datetime(p.datetime).dt.strftime("%Y%m%d")
    x = p.merge(panel[["datetime", "instrument", "label60"]], on=["datetime", "instrument"], how="inner")
    ic = x.groupby("datetime").apply(lambda g: g["pred"].corr(g["label60"], method="spearman"), include_groups=False).dropna()
    return {"days": int(ic.size), "mean_rank_ic": float(ic.mean()) if len(ic) else None,
            "rank_ic_std": float(ic.std(ddof=0)) if len(ic) else None,
            "rank_ic_ir": float(ic.mean() / ic.std(ddof=0)) if len(ic) and ic.std(ddof=0) else None}


def main() -> None:
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    warnings.filterwarnings("ignore", category=FutureWarning)
    panel_path, bars_path = OUT / "candidate_panel.parquet", OUT / "candidate_bars.parquet"
    benchmark_daily = None
    benchmark_path = ROOT / "wj_backtest_results" / "trend_equity_curve.csv"
    if benchmark_path.exists():
        benchmark = pd.read_csv(benchmark_path, dtype={"trade_date": str})
        benchmark["trade_date"] = benchmark.trade_date.str.replace("-", "", regex=False)
        benchmark_daily = benchmark.set_index("trade_date")["benchmark_equity"].sort_index().pct_change().fillna(0)
    if panel_path.exists() and bars_path.exists():
        panel, bars = pd.read_parquet(panel_path), pd.read_parquet(bars_path)
        log(f"loaded cached candidates {len(panel):,}, price rows {len(bars):,}")
    else:
        daily, basic = load_prices()
        panel, bars = build_candidates(daily, basic)
        del daily, basic
    study = optuna.create_study(direction="maximize", study_name="ww_qlib_walkforward",
                                storage=f"sqlite:///{(OUT / 'optuna.sqlite').as_posix()}", load_if_exists=True)
    trial_budget = int(os.environ.get("WW_TRIAL_BUDGET", "20"))
    completed = sum(t.state == optuna.trial.TrialState.COMPLETE for t in study.trials)
    trials = max(0, trial_budget - completed)
    t0 = time.time()

    def objective(trial: optuna.Trial) -> float:
        window = trial.suggest_categorical("breakout_window", [60, 90, 120, 180])
        vol_min = trial.suggest_float("vol_min", 0.9, 2.2, step=0.1)
        stop_pct = trial.suggest_float("stop_pct", 0.06, 0.12, step=0.01)
        max_hold = trial.suggest_categorical("max_hold", [40, 60, 80, 100])
        topk = trial.suggest_categorical("topk", [5, 8, 10, 15, 20])
        filtered = panel[(panel[f"break_{window}"] == 1) & (panel.signal_vol_ratio >= vol_min)].copy()
        if filtered.empty:
            return -10.0
        model_params = {
            "num_leaves": trial.suggest_int("num_leaves", 7, 31),
            "max_depth": trial.suggest_int("max_depth", 2, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.12, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.65, 1.0),
            "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 10.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 20.0),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 120),
            "num_threads": 3,
            "num_boost_round": trial.suggest_int("num_boost_round", 80, 300),
        }
        pred, fitinfo = fit_predict(filtered, model_params, TRAIN_CUTOFF, VALID_START, VALID_END, "valid")
        metrics, _, trades = portfolio_backtest(pred, filtered, bars, topk, stop_pct, max_hold,
                                                VALID_START, VALID_END, benchmark_daily)
        ric = rank_ic(pred, filtered)
        # Penalize low breadth and deep drawdown; validation is for selection only, 2026 stays sealed.
        sharpe = metrics.get("sharpe_zero_rf") or -2.0
        score = sharpe + 0.15 * metrics.get("annualized_return", -1) + 0.25 * metrics.get("max_drawdown", -1)
        if metrics.get("trades", 0) < 20:
            score -= 0.75
        trial.set_user_attr("portfolio", metrics)
        trial.set_user_attr("rank_ic", ric)
        trial.set_user_attr("fit", fitinfo)
        log(f"trial {trial.number+1}/{trials}: score={score:.3f}, val_ret={metrics.get('total_return')}, trades={metrics.get('trades')}, IC={ric.get('mean_rank_ic')}")
        return float(score)

    with _workflow_stub.R.start(experiment_name="WW Qlib price-proxy walk-forward"):
        _workflow_stub.R.log_params(data_start=START, data_end=END, train_cutoff=TRAIN_CUTOFF,
                     validation=f"{VALID_START}:{VALID_END}", test=f"{TEST_START}:{END}",
                     label="next-open-to-60-session-close", cost=ROUND_TRIP_COST,
                     max_positions=MAX_POSITIONS, trials=trials, data_rows=len(panel))
        if trials:
            study.optimize(objective, n_trials=trials, gc_after_trial=True)
        best = study.best_trial
        bp = dict(best.params)
        model_params = {k: bp[k] for k in ["num_leaves", "max_depth", "learning_rate", "feature_fraction",
                                            "lambda_l1", "lambda_l2", "min_data_in_leaf"]}
        model_params.update(num_threads=3, num_boost_round=bp["num_boost_round"])
        testpanel = panel[(panel[f"break_{bp['breakout_window']}"] == 1) & (panel.signal_vol_ratio >= bp["vol_min"])].copy()
        # Keep the 2026 holdout fully sealed: train through H1 2025, early-stop on H2 2025,
        # then predict 2026 without reading holdout labels for fitting or early stopping.
        pred, fitinfo = fit_predict(testpanel, model_params, TRAIN_CUTOFF, VALID_START, VALID_END, "test")
        ric = rank_ic(pred, testpanel)
        metrics, curve, trades = portfolio_backtest(pred, testpanel, bars, bp["topk"], bp["stop_pct"],
                                                    bp["max_hold"], TEST_START, TEST_LAST_SIGNAL, benchmark_daily)
        # Baseline preserves C entry/exit, ranking by causal 60-session momentum only.
        q = testpanel.set_index([pd.to_datetime(testpanel.datetime), "instrument"])
        baseline_pred = q["mom60"].reindex(pred.index)
        baseline_metrics, baseline_curve, baseline_trades = portfolio_backtest(
            baseline_pred, testpanel, bars, bp["topk"], bp["stop_pct"], bp["max_hold"],
            TEST_START, TEST_LAST_SIGNAL, benchmark_daily)
        # Ranking ablations isolate whether the learned ordering adds value within the same
        # candidate pool and execution rules. These are diagnostics, never used to retune.
        rank_ablations = {}
        rankers = {
            "reverse_model_score": -pred,
            "momentum_120": q["mom120"].reindex(pred.index),
            "breakout_extension": (q["close"] / q["breakout_level"] - 1).reindex(pred.index),
        }
        for name, ranker in rankers.items():
            rank_metrics, _, _ = portfolio_backtest(ranker, testpanel, bars, bp["topk"], bp["stop_pct"],
                                                      bp["max_hold"], TEST_START, TEST_LAST_SIGNAL, benchmark_daily)
            rank_ablations[name] = rank_metrics
        random_returns = []
        for seed in range(100):
            random_rank = pd.Series(np.random.default_rng(SEED + seed).standard_normal(len(pred)), index=pred.index)
            random_metrics, _, _ = portfolio_backtest(random_rank, testpanel, bars, bp["topk"], bp["stop_pct"],
                                                       bp["max_hold"], TEST_START, TEST_LAST_SIGNAL, benchmark_daily)
            random_returns.append(random_metrics.get("total_return", 0.0))
        rank_ablations["random_100_total_return"] = {
            "median": float(np.median(random_returns)), "p10": float(np.quantile(random_returns, 0.1)),
            "p90": float(np.quantile(random_returns, 0.9)), "runs": len(random_returns),
            "model_return_percentile": float(np.mean(np.asarray(random_returns) <= metrics.get("total_return", 0.0)))}
        report = {
            "framework": "Qlib DatasetH + StaticDataLoader + LGBModel; Optuna TPE stores trial parameters and metrics",
            "scope": "Causal daily-price proxy for WW leader identification and C.3/C.4 mechanical execution only; no point-in-time fundamentals, historic sector membership, or human mainline judgments.",
            "data": {"bars": int(len(bars)), "candidate_panel_rows": int(len(panel)), "start": START, "end": END,
                     "train_cutoff": TRAIN_CUTOFF, "validation": [VALID_START, VALID_END],
                     "test_signals": [TEST_START, TEST_LAST_SIGNAL], "label": "next open to 60th session close",
                     "round_trip_cost": ROUND_TRIP_COST, "max_positions": MAX_POSITIONS},
            "best_validation": {"objective": best.value, "parameters": bp,
                                "portfolio": best.user_attrs.get("portfolio"),
                                "rank_ic": best.user_attrs.get("rank_ic")},
            "optimization": {"trial_budget": trial_budget,
                             "completed_trials": sum(t.state == optuna.trial.TrialState.COMPLETE for t in study.trials)},
            "holdout_test": {"portfolio": metrics, "rank_ic": ric, "fit": fitinfo,
                             "baseline_causal_mom60": baseline_metrics,
                             "rank_ablation_same_candidates_same_execution": rank_ablations},
            "interpretation": "The holdout is only 2026-01 to 2026-06 because the 60-session label must mature by 2026-08. Final model trains through 2025-06 and uses 2025-H2 only for early stopping; no 2026 labels enter fitting. This is one short regime and not proof of durable alpha.",
            "elapsed_seconds": round(time.time() - t0, 1),
        }
        (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        trial_rows = []
        for item in study.trials:
            portfolio = item.user_attrs.get("portfolio", {})
            ic = item.user_attrs.get("rank_ic", {})
            trial_rows.append({"trial": item.number, "state": item.state.name, "objective": item.value,
                               **item.params, "validation_return": portfolio.get("total_return"),
                               "validation_drawdown": portfolio.get("max_drawdown"),
                               "validation_sharpe": portfolio.get("sharpe_zero_rf"),
                               "validation_trades": portfolio.get("trades"),
                               "validation_rank_ic": ic.get("mean_rank_ic")})
        pd.DataFrame(trial_rows).to_csv(OUT / "optimization_trials.csv", index=False)
        curve.to_csv(OUT / "holdout_equity.csv", index=False)
        trades.to_csv(OUT / "holdout_trades.csv", index=False)
        baseline_curve.to_csv(OUT / "baseline_equity.csv", index=False)
        baseline_trades.to_csv(OUT / "baseline_trades.csv", index=False)
        _workflow_stub.R.log_metrics(holdout_return=metrics.get("total_return", 0),
                      holdout_sharpe=metrics.get("sharpe_zero_rf", 0) or 0,
                      holdout_max_drawdown=metrics.get("max_drawdown", 0),
                      holdout_rank_ic=ric.get("mean_rank_ic", 0) or 0)
        _workflow_stub.R.save_objects(report=report, holdout_equity=curve, holdout_trades=trades)
        log(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
