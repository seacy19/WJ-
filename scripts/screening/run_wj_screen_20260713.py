import json
import math
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import tushare as ts


ROOT = Path(__file__).resolve().parent
SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a"
    r"\market_data_mcp\.market_data_mcp_secrets.json"
)
CACHE_DB = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a"
    r"\data\tushare_cache.sqlite"
)
TODAY = "20260713"
LOOKBACK_START = "20260601"


def load_token() -> str:
    data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    token = data.get("TUSHARE_TOKEN") or data.get("TUSHARE_PRO_TOKEN")
    if not token:
        raise RuntimeError("TuShare token not found in local secret file.")
    return token


def cached(api_name: str, params: dict, fields: str | None = None):
    if not CACHE_DB.exists():
        return None
    con = sqlite3.connect(CACHE_DB)
    params_json = json.dumps(params, ensure_ascii=False, sort_keys=True)
    row = con.execute(
        """
        SELECT rows_json FROM api_cache
        WHERE api_name = ? AND params_json = ? AND ifnull(fields, '') = ifnull(?, '')
        ORDER BY fetched_at DESC LIMIT 1
        """,
        (api_name, params_json, fields or ""),
    ).fetchone()
    if not row:
        return None
    return pd.DataFrame(json.loads(row[0]))


def pro_query(pro, api_name: str, params: dict, fields: str | None = None) -> pd.DataFrame:
    cached_df = cached(api_name, params, fields)
    if cached_df is not None:
        return cached_df
    fn = getattr(pro, api_name, None)
    if fn is None:
        return pro.query(api_name, **params, fields=fields)
    call_params = dict(params)
    if fields:
        call_params["fields"] = fields
    return fn(**call_params)


def to_num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def expma_status(mins: pd.DataFrame) -> dict:
    if mins.empty or len(mins) < 50:
        return {
            "status": "无法稳定判断",
            "detail": f"15分钟K线仅{len(mins)}根，少于EXPMA50需要的50根",
            "bars": int(len(mins)),
        }
    x = mins.sort_values("trade_time").copy()
    x["close"] = pd.to_numeric(x["close"], errors="coerce")
    x["expma12"] = x["close"].ewm(span=12, adjust=False).mean()
    x["expma50"] = x["close"].ewm(span=50, adjust=False).mean()
    x["state"] = x["expma12"] > x["expma50"]
    last = x.iloc[-1]
    prev = x.iloc[-2]
    recent = x.tail(17)
    recent_positive = int(recent["state"].sum())
    crosses = int((recent["state"] != recent["state"].shift()).sum() - 1)
    latest_state = "金叉/短线偏强" if bool(last["state"]) else "死叉/短线偏弱"
    if bool(last["state"]) and not bool(prev["state"]):
        latest_state = "最新一根刚金叉"
    elif (not bool(last["state"])) and bool(prev["state"]):
        latest_state = "最新一根刚死叉"
    return {
        "status": latest_state,
        "latest_time": str(last["trade_time"]),
        "close": float(last["close"]),
        "expma12": float(last["expma12"]),
        "expma50": float(last["expma50"]),
        "recent_17_positive_bars": recent_positive,
        "recent_17_crosses": max(crosses, 0),
        "bars": int(len(x)),
    }


def fmt_money(v):
    if pd.isna(v):
        return None
    return round(float(v) / 10000, 2)


def main():
    pro = ts.pro_api(load_token())

    fields_daily = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
    fields_basic = "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pb,total_mv,circ_mv"
    fields_stock = "ts_code,symbol,name,area,industry,market,list_date"
    fields_limit = "trade_date,ts_code,up_limit,down_limit"

    cal = pro.trade_cal(exchange="SSE", start_date=LOOKBACK_START, end_date=TODAY,
                        fields="exchange,cal_date,is_open,pretrade_date")
    open_days = cal[cal["is_open"] == 1]["cal_date"].sort_values().tolist()
    latest_complete = TODAY
    latest_basic = pro.daily_basic(trade_date=TODAY, fields=fields_basic)
    if latest_basic.empty:
        latest_complete = max(d for d in open_days if d < TODAY)

    days = [d for d in open_days if d <= latest_complete][-25:]
    daily_frames = []
    limit_frames = []
    for d in days:
        if d == latest_complete:
            daily_frames.append(pro_query(pro, "daily", {"trade_date": d}, fields_daily))
            limit_frames.append(pro_query(pro, "stk_limit", {"trade_date": d}, fields_limit))
        else:
            daily_frames.append(pro.daily(trade_date=d, fields=fields_daily))
            try:
                limit_frames.append(pro.stk_limit(trade_date=d, fields=fields_limit))
            except Exception:
                pass

    daily = pd.concat(daily_frames, ignore_index=True)
    limits = pd.concat(limit_frames, ignore_index=True) if limit_frames else pd.DataFrame()
    daily = to_num(daily, ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"])
    limits = to_num(limits, ["up_limit", "down_limit"])

    latest_daily = daily[daily["trade_date"] == latest_complete].copy()
    latest_basic = pro_query(pro, "daily_basic", {"trade_date": latest_complete}, fields_basic)
    latest_basic = to_num(latest_basic, ["turnover_rate", "turnover_rate_f", "volume_ratio", "pe", "pb", "total_mv", "circ_mv"])
    stocks = pro_query(pro, "stock_basic", {"exchange": "", "list_status": "L"}, fields_stock)

    latest_limits = limits[limits["trade_date"] == latest_complete].drop_duplicates("ts_code")
    latest = (
        latest_daily.merge(latest_basic, on=["ts_code", "trade_date"], how="left")
        .merge(stocks, on="ts_code", how="left")
        .merge(latest_limits, on="ts_code", how="left")
    )
    latest["is_st"] = latest["name"].fillna("").str.contains("ST", case=False, regex=False)
    latest["is_limit_up"] = (
        latest["up_limit"].notna()
        & (latest["close"] >= latest["up_limit"] * 0.999)
        & (latest["pct_chg"] > 0)
    )
    latest["is_touched_limit"] = latest["up_limit"].notna() & (latest["high"] >= latest["up_limit"] * 0.999)

    daily_sorted = daily.sort_values(["ts_code", "trade_date"]).copy()
    daily_sorted["ma5"] = daily_sorted.groupby("ts_code")["close"].transform(lambda s: s.rolling(5).mean())
    daily_sorted["ma10"] = daily_sorted.groupby("ts_code")["close"].transform(lambda s: s.rolling(10).mean())
    daily_sorted["close_10ago"] = daily_sorted.groupby("ts_code")["close"].shift(10)
    daily_sorted["close_20ago"] = daily_sorted.groupby("ts_code")["close"].shift(20)
    daily_sorted["pct_10d"] = (daily_sorted["close"] / daily_sorted["close_10ago"] - 1) * 100
    daily_sorted["pct_20d"] = (daily_sorted["close"] / daily_sorted["close_20ago"] - 1) * 100
    metrics = daily_sorted[daily_sorted["trade_date"] == latest_complete][
        ["ts_code", "ma5", "ma10", "pct_10d", "pct_20d"]
    ]
    latest = latest.merge(metrics, on="ts_code", how="left")
    latest["ma_zone"] = (latest["close"] >= latest["ma5"]) & (latest["close"] <= latest["ma10"])
    latest["amount_yi"] = latest["amount"] / 100000
    latest["total_mv_yi"] = latest["total_mv"] / 10000

    # Consecutive limit-up days ending at latest complete date.
    marked = daily.merge(limits, on=["ts_code", "trade_date"], how="left")
    marked = to_num(marked, ["close", "pct_chg", "up_limit"])
    marked["limit_up"] = marked["up_limit"].notna() & (marked["close"] >= marked["up_limit"] * 0.999) & (marked["pct_chg"] > 0)
    consec = {}
    for code, g in marked.sort_values("trade_date").groupby("ts_code"):
        count = 0
        for _, row in g.tail(len(days)).iloc[::-1].iterrows():
            if bool(row["limit_up"]):
                count += 1
            else:
                break
        consec[code] = count
    latest["limit_up_streak"] = latest["ts_code"].map(consec).fillna(0).astype(int)

    clean = latest[~latest["is_st"]].copy()
    liquid = clean[clean["amount"] >= 50000].copy()
    limit_ups = liquid[liquid["is_limit_up"]].copy()
    touched = liquid[liquid["is_touched_limit"] & ~liquid["is_limit_up"]].copy()

    industry_counts = Counter(limit_ups["industry"].dropna())
    industry_table = [
        {"industry": k, "limit_up_count": v}
        for k, v in industry_counts.most_common(20)
    ]

    emotion_pool = limit_ups[
        (limit_ups["total_mv_yi"].between(50, 300))
        & (limit_ups["turnover_rate"].between(5, 15))
    ].copy()
    emotion_pool["industry_limit_count"] = emotion_pool["industry"].map(industry_counts).fillna(0).astype(int)
    emotion_pool["score"] = (
        emotion_pool["industry_limit_count"] * 10
        + emotion_pool["amount_yi"].rank(pct=True) * 5
        + emotion_pool["volume_ratio"].fillna(0).clip(0, 5)
        + emotion_pool["ma_zone"].astype(int) * 2
    )

    buz_leaders = liquid[(liquid["pct_10d"] >= 50) | (liquid["limit_up_streak"] >= 6)].copy()
    buz_leaders["b1_reason"] = buz_leaders.apply(
        lambda r: "10日涨幅>=50%" if (not pd.isna(r["pct_10d"]) and r["pct_10d"] >= 50) else "连板>=6天",
        axis=1,
    )
    buz_leaders = buz_leaders.sort_values(["pct_10d", "limit_up_streak", "amount_yi"], ascending=False)

    buz_candidates = liquid[
        (liquid["pct_20d"].notna())
        & (liquid["pct_20d"] <= 20)
        & (liquid["volume_ratio"].fillna(0) >= 1.5)
        & (liquid["total_mv_yi"] <= 100)
    ].copy()
    if not buz_leaders.empty:
        leader_industries = set(buz_leaders["industry"].dropna())
        buz_candidates["same_industry_with_b1"] = buz_candidates["industry"].isin(leader_industries)
    else:
        buz_candidates["same_industry_with_b1"] = False
    buz_candidates["score"] = (
        buz_candidates["same_industry_with_b1"].astype(int) * 10
        + buz_candidates["volume_ratio"].fillna(0).clip(0, 6)
        + buz_candidates["turnover_rate"].fillna(0).clip(0, 20) / 4
        + buz_candidates["ma_zone"].astype(int) * 2
    )
    buz_candidates = buz_candidates.sort_values(["same_industry_with_b1", "score", "amount_yi"], ascending=False)

    trend_pool = liquid[
        (liquid["pct_20d"].notna())
        & (liquid["pct_20d"] >= 20)
        & (liquid["close"] >= liquid.groupby("ts_code")["close"].transform("max") if False else True)
    ].copy()
    # Use 25-day high proxy; true historical high needs longer history and fundamental logic confirmation.
    rolling_high = daily_sorted.groupby("ts_code")["close"].transform(lambda s: s.rolling(25, min_periods=5).max())
    high25 = daily_sorted.assign(high25=rolling_high)
    high25 = high25[high25["trade_date"] == latest_complete][["ts_code", "high25"]]
    latest = latest.merge(high25, on="ts_code", how="left")
    trend_pool = latest[(~latest["is_st"]) & (latest["amount"] >= 50000) & (latest["close"] >= latest["high25"] * 0.995)].copy()
    trend_pool = trend_pool.sort_values(["pct_20d", "amount_yi"], ascending=False)

    mins_status = {}
    try:
        mins = pro.query(
            "stk_mins",
            ts_code="000001.SH",
            freq="15min",
            start_date=f"{days[0]} 09:30:00",
            end_date=f"{latest_complete} 15:00:00",
            fields="ts_code,trade_time,open,high,low,close,vol,amount",
        )
        mins_status = expma_status(mins)
    except Exception as exc:
        mins_status = {"status": "无法取数", "detail": f"{type(exc).__name__}: {exc}"}

    def rows(df: pd.DataFrame, n: int):
        keep = [
            "ts_code", "name", "industry", "market", "close", "pct_chg",
            "amount_yi", "total_mv_yi", "turnover_rate", "volume_ratio",
            "pct_10d", "pct_20d", "ma_zone", "limit_up_streak",
            "industry_limit_count", "b1_reason", "same_industry_with_b1", "score",
        ]
        out = []
        for _, r in df.head(n).iterrows():
            item = {}
            for col in keep:
                if col in df.columns:
                    v = r.get(col)
                    if isinstance(v, (float, int)) and not isinstance(v, bool):
                        item[col] = None if pd.isna(v) or math.isinf(v) else round(float(v), 4)
                    elif pd.isna(v):
                        item[col] = None
                    else:
                        item[col] = bool(v) if isinstance(v, (bool,)) else v
            out.append(item)
        return out

    result = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "requested_today": TODAY,
        "latest_complete_trade_date": latest_complete,
        "today_daily_basic_rows": int(len(latest_basic)) if latest_complete == TODAY else 0,
        "data_summary": {
            "daily_rows": int(len(daily)),
            "latest_daily_rows": int(len(latest_daily)),
            "latest_liquid_non_st_rows": int(len(liquid)),
            "limit_up_liquid_non_st_rows": int(len(limit_ups)),
            "touched_but_not_closed_limit_rows": int(len(touched)),
            "b1_leaders_rows": int(len(buz_leaders)),
            "buz_candidates_rows": int(len(buz_candidates)),
        },
        "market_expma_15m": mins_status,
        "industry_limit_up_proxy": industry_table,
        "emotion_leader_pool": rows(emotion_pool.sort_values("score", ascending=False), 20),
        "buzhang_b1_leaders": rows(buz_leaders, 20),
        "buzhang_observation_pool": rows(buz_candidates, 30),
        "trend_25d_high_proxy": rows(trend_pool, 20),
        "data_gaps": [
            "20260713盘前TuShare daily_basic暂无今日行，使用20260710收盘作为最新完整交易日。",
            "真实题材不能直接用行业标签替代；本报告的industry_limit_up_proxy只用于发现线索。",
            "limit_list_d无权限；涨停/连板用stk_limit涨停价与日线收盘价计算。",
            "盘中买点如分时涨幅<=2%、盘中大单/放量，需要今日盘中实时复核。",
            "基本面龙头分支需要行业盈利中枢抬升证据；本报告只给25日新高线索，不给正式基本面龙头结论。",
        ],
    }

    out_json = ROOT / "WJ策略_20260713_盘前筛选结果.json"
    out_md = ROOT / "WJ策略_20260713_盘前筛选结果.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# WJ策略 2026-07-13 盘前筛选结果",
        "",
        f"- 请求日期：{TODAY}",
        f"- 最新完整交易日：{latest_complete}",
        f"- 15分钟EXPMA：{mins_status}",
        "",
        "## 数据缺口",
    ]
    lines.extend([f"- {x}" for x in result["data_gaps"]])
    lines.append("")
    lines.append("## 行业涨停聚集度线索（非真实题材结论）")
    for x in industry_table[:15]:
        lines.append(f"- {x['industry']}: {x['limit_up_count']}只")
    lines.append("")
    lines.append("## 情绪龙头候选池（需人工确认真实题材≥8只）")
    for x in result["emotion_leader_pool"][:15]:
        lines.append(
            f"- {x.get('ts_code')} {x.get('name')}｜{x.get('industry')}｜收盘{x.get('close')}｜"
            f"市值{x.get('total_mv_yi')}亿｜换手{x.get('turnover_rate')}%｜量比{x.get('volume_ratio')}｜"
            f"成交{x.get('amount_yi')}亿｜连板{x.get('limit_up_streak')}｜行业涨停线索{x.get('industry_limit_count')}"
        )
    lines.append("")
    lines.append("## 补涨级龙头 B.1 候选（先确认断板/资金外溢）")
    for x in result["buzhang_b1_leaders"][:15]:
        lines.append(
            f"- {x.get('ts_code')} {x.get('name')}｜{x.get('industry')}｜{x.get('b1_reason')}｜"
            f"10日{x.get('pct_10d')}%｜连板{x.get('limit_up_streak')}｜成交{x.get('amount_yi')}亿"
        )
    lines.append("")
    lines.append("## 补涨观察池（低位+放量线索，盘中≤2%再看）")
    for x in result["buzhang_observation_pool"][:20]:
        lines.append(
            f"- {x.get('ts_code')} {x.get('name')}｜{x.get('industry')}｜20日{x.get('pct_20d')}%｜"
            f"市值{x.get('total_mv_yi')}亿｜量比{x.get('volume_ratio')}｜换手{x.get('turnover_rate')}%｜"
            f"同B1行业{x.get('same_industry_with_b1')}"
        )
    lines.append("")
    lines.append("## 基本面龙头线索（25日新高代理，不是正式结论）")
    for x in result["trend_25d_high_proxy"][:15]:
        lines.append(
            f"- {x.get('ts_code')} {x.get('name')}｜{x.get('industry')}｜20日{x.get('pct_20d')}%｜"
            f"成交{x.get('amount_yi')}亿｜市值{x.get('total_mv_yi')}亿"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "latest_complete_trade_date": latest_complete,
        "market_expma_15m": mins_status,
        "emotion_pool": len(result["emotion_leader_pool"]),
        "b1_leaders": len(result["buzhang_b1_leaders"]),
        "buzhang_pool": len(result["buzhang_observation_pool"]),
        "out_json": str(out_json),
        "out_md": str(out_md),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
