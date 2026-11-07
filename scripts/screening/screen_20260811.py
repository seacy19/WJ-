import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
TRADE_DATE = os.environ.get("WJ_TRADE_DATE", "20260810")
OUT = Path(os.environ.get("WJ_OUTPUT", "screen_20260811_output.json"))


def nfloat(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
token = secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN")
pro = ts.pro_api(token)

basic = pro.stock_basic(
    exchange="",
    list_status="L",
    fields="ts_code,name,industry,market,list_date",
)
daily_basic = pro.daily_basic(
    trade_date=TRADE_DATE,
    fields=(
        "ts_code,trade_date,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps_ttm,"
        "total_mv,circ_mv"
    ),
)
cal = pro.trade_cal(
    exchange="SSE",
    start_date="20260701",
    end_date=TRADE_DATE,
    is_open="1",
    fields="cal_date,is_open",
)
dates = sorted(cal["cal_date"].tolist())[-16:]
daily_frames = []
for date in dates:
    frame = pro.daily(
        trade_date=date,
        fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
    )
    daily_frames.append(frame)
daily = pd.concat(daily_frames, ignore_index=True)
daily = daily.merge(basic, on="ts_code", how="left")
daily["is_st"] = daily["name"].fillna("").str.contains("ST")
daily = daily[~daily["is_st"]].copy()

try:
    limits = pro.limit_list_d(
        trade_date=TRADE_DATE,
        limit_type="U",
        fields=(
            "trade_date,ts_code,name,industry,close,pct_chg,amount,first_time,"
            "last_time,open_times,up_stat,limit_times"
        ),
    )
    limits = limits[~limits["name"].fillna("").str.contains("ST")].copy()
except Exception as exc:
    limits = pd.DataFrame()
    limit_error = str(exc)

piv = daily.pivot_table(index="ts_code", columns="trade_date", values="close", aggfunc="last")
latest = daily[daily["trade_date"] == TRADE_DATE].copy()
latest = latest.merge(daily_basic, on=["ts_code", "trade_date"], how="left")
latest = latest.set_index("ts_code")
for n in (5, 10, 15):
    if len(dates) > n:
        ref = dates[-(n + 1)]
        latest[f"ret{n}"] = latest["close"] / piv[ref] * 100 - 100

limit_counts = {}
if not limits.empty:
    limit_counts = limits.groupby("industry").size().to_dict()

industry_rows = []
for industry, g in latest.groupby("industry", dropna=False):
    if len(g) < 5:
        continue
    industry_rows.append(
        {
            "industry": industry,
            "count": int(len(g)),
            "mean_pct": nfloat(g["pct_chg"].mean()),
            "median_pct": nfloat(g["pct_chg"].median()),
            "advance_ratio": nfloat((g["pct_chg"] > 0).mean()),
            "mean_ret5": nfloat(g["ret5"].mean()),
            "median_ret5": nfloat(g["ret5"].median()),
            "mean_ret10": nfloat(g["ret10"].mean()),
            "median_ret10": nfloat(g["ret10"].median()),
            "limit_up_count": int(limit_counts.get(industry, 0)),
            "amount_bn": nfloat(g["amount"].sum() / 100000),
        }
    )
industries = pd.DataFrame(industry_rows)
industries["strength_score"] = (
    industries["median_pct"] * 1.2
    + industries["median_ret5"] * 0.7
    + industries["median_ret10"] * 0.35
    + industries["limit_up_count"] * 0.7
    + industries["advance_ratio"] * 2
)
industries = industries.sort_values("strength_score", ascending=False)

# Build a broad mid/large-cap pool, then perform qfq curve checks only on the
# most relevant names to keep the data call set bounded.
pool = latest[
    (latest["total_mv"] >= 4_000_000)  # >= RMB40bn
    & (latest["total_mv"] <= 80_000_000)  # <= RMB800bn
].copy()
industry_score = industries.set_index("industry")["strength_score"]
pool["industry_score"] = pool["industry"].map(industry_score).fillna(0)
pool["amount_rank"] = pool["amount"].rank(pct=True)
pool["candidate_score"] = (
    pool["industry_score"]
    + pool["ret5"].clip(-15, 30) * 0.45
    + pool["ret10"].clip(-20, 50) * 0.20
    + pool["pct_chg"].clip(-10, 10) * 0.25
    + pool["amount_rank"] * 2
)
codes = pool.sort_values("candidate_score", ascending=False).head(90).index.tolist()

# Always include previously discussed and representative quality names.
must_include = [
    "603259.SH", "603296.SH", "603228.SH", "002475.SZ", "300308.SZ",
    "300502.SZ", "300476.SZ", "300394.SZ", "300750.SZ", "000333.SZ",
    "600519.SH", "600760.SH", "600893.SH", "002371.SZ", "601138.SH",
    "601689.SH", "002050.SZ", "688111.SH", "688008.SH", "688012.SH",
]
codes = list(dict.fromkeys(codes + must_include))

curve_rows = []
for code in codes:
    try:
        df = ts.pro_bar(
            api=pro,
            ts_code=code,
            start_date="20250601",
            end_date=TRADE_DATE,
            adj="qfq",
        )
        if df is None or df.empty:
            continue
        df = df.sort_values("trade_date")
        closes = df["close"].astype(float).reset_index(drop=True)
        vols = df["vol"].astype(float).reset_index(drop=True)
        last = float(closes.iloc[-1])
        mas = {w: (float(closes.iloc[-w:].mean()) if len(closes) >= w else None) for w in (5, 10, 20, 60, 120, 250)}
        slopes = {}
        for w in (20, 60, 120, 250):
            if len(closes) >= w + 20:
                old = float(closes.iloc[-(w + 20):-20].mean())
                slopes[w] = (mas[w] / old - 1) * 100
            else:
                slopes[w] = None
        meta = latest.loc[code] if code in latest.index else None
        full_values = [last] + [mas[w] for w in (5, 10, 20, 60, 120, 250)]
        full_curve = all(v is not None for v in full_values) and all(
            full_values[i] >= full_values[i + 1] for i in range(len(full_values) - 1)
        )
        long_curve = all(mas[w] is not None for w in (20, 60, 120, 250)) and (
            last >= mas[20] >= mas[60] >= mas[120] >= mas[250]
        )
        all_slopes = all(slopes[w] is not None and slopes[w] > 0 for w in (20, 60, 120, 250))
        high250 = float(closes.iloc[-250:].max()) if len(closes) >= 250 else float(closes.max())
        curve_rows.append(
            {
                "code": code,
                "name": None if meta is None else meta["name"],
                "industry": None if meta is None else meta["industry"],
                "close": last,
                "pct": None if meta is None else nfloat(meta["pct_chg"]),
                "market_cap_yi": None if meta is None else nfloat(meta["total_mv"] / 10000),
                "pe_ttm": None if meta is None else nfloat(meta["pe_ttm"]),
                "pb": None if meta is None else nfloat(meta["pb"]),
                "turnover": None if meta is None else nfloat(meta["turnover_rate"]),
                "volume_ratio": None if meta is None else nfloat(meta["volume_ratio"]),
                "amount_bn": None if meta is None else nfloat(meta["amount"] / 100000),
                "ret5": None if meta is None else nfloat(meta["ret5"]),
                "ret10": None if meta is None else nfloat(meta["ret10"]),
                **{f"ma{w}": mas[w] for w in (5, 10, 20, 60, 120, 250)},
                **{f"ma{w}_slope20": slopes[w] for w in (20, 60, 120, 250)},
                "full_curve": full_curve,
                "long_curve": long_curve,
                "all_long_slopes_up": all_slopes,
                "drawdown250": (last / high250 - 1) * 100,
                "vol5_ratio": float(vols.iloc[-1] / vols.iloc[-6:-1].mean()) if len(vols) >= 6 else None,
            }
        )
    except Exception as exc:
        curve_rows.append({"code": code, "error": str(exc)})

result = {
    "trade_date": TRADE_DATE,
    "dates": dates,
    "market": {
        "count": int(len(latest)),
        "advance": int((latest["pct_chg"] > 0).sum()),
        "decline": int((latest["pct_chg"] < 0).sum()),
        "median_pct": nfloat(latest["pct_chg"].median()),
        "amount_bn": nfloat(latest["amount"].sum() / 100000),
        "limit_up_count": int(len(limits)) if not limits.empty else None,
    },
    "top_industries": industries.head(25).to_dict(orient="records"),
    "bottom_industries": industries.tail(15).sort_values("strength_score").to_dict(orient="records"),
    "limit_ups": limits.to_dict(orient="records") if not limits.empty else [],
    "limit_error": locals().get("limit_error"),
    "top_large_candidates": pool.sort_values("candidate_score", ascending=False)
        .head(60)
        .reset_index()[["ts_code", "name", "industry", "close", "pct_chg", "ret5", "ret10", "total_mv", "pe_ttm", "pb", "amount", "candidate_score"]]
        .to_dict(orient="records"),
    "curve_candidates": curve_rows,
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(OUT.resolve()), "market": result["market"], "curve_count": len(curve_rows)}, ensure_ascii=False, indent=2))
