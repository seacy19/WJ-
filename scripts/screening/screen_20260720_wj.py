import json
from pathlib import Path

import pandas as pd
import tushare as ts


DATE = "20260717"
START = "20260701"
SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp"
    r"\.market_data_mcp_secrets.json"
)


def get_token():
    values = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    return values.get("TUSHARE_TOKEN") or values.get("TUSHARE_PRO_TOKEN")


def limit_up(row):
    name = str(row.get("name", "")).upper()
    code = str(row["ts_code"])
    pct = float(row["pct_chg"])
    if "ST" in name:
        return pct >= 4.8
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.endswith(".BJ"):
        return pct >= 29.5
    return pct >= 9.5


def main():
    pro = ts.pro_api(get_token())
    fields = "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount"
    stocks = pro.stock_basic(
        exchange="", list_status="L",
        fields="ts_code,symbol,name,industry,market,list_date",
    )
    frames = []
    for day in pd.date_range("2026-07-01", "2026-07-17", freq="B"):
        frame = pro.daily(trade_date=day.strftime("%Y%m%d"), fields=fields)
        if not frame.empty:
            frames.append(frame)
    hist = pd.concat(frames, ignore_index=True).merge(stocks, on="ts_code", how="left")
    numeric = ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]
    hist[numeric] = hist[numeric].apply(pd.to_numeric, errors="coerce")
    hist = hist.sort_values(["ts_code", "trade_date"])
    hist["limit_up"] = hist.apply(limit_up, axis=1)
    grouped = hist.groupby("ts_code", group_keys=False)
    for n in [5, 10]:
        hist[f"ma{n}"] = grouped["close"].transform(lambda s, n=n: s.rolling(n).mean())
    hist["close_10ago"] = grouped["close"].shift(10)
    hist["ret10"] = (hist["close"] / hist["close_10ago"] - 1) * 100
    hist["vol_ma5"] = grouped["vol"].transform(lambda s: s.rolling(5).mean())
    hist["high10"] = grouped["high"].transform(lambda s: s.rolling(10).max())

    dates = sorted(hist["trade_date"].unique())
    today_date, prev_date = dates[-1], dates[-2]
    today = hist[hist["trade_date"] == today_date].copy()
    prev = hist[hist["trade_date"] == prev_date][["ts_code", "limit_up"]].rename(
        columns={"limit_up": "prev_limit"}
    )
    today = today.merge(prev, on="ts_code", how="left")
    basic = pro.daily_basic(
        trade_date=DATE,
        fields="ts_code,turnover_rate,volume_ratio,pe_ttm,pb,total_mv,circ_mv",
    )
    today = today.merge(basic, on="ts_code", how="left")
    today["amount_yi"] = today["amount"] / 100000
    today["total_mv_yi"] = pd.to_numeric(today["total_mv"], errors="coerce") / 10000
    today["turnover_rate"] = pd.to_numeric(today["turnover_rate"], errors="coerce")
    today["volume_ratio"] = pd.to_numeric(today["volume_ratio"], errors="coerce")

    def consecutive_limits(code):
        flags = hist.loc[hist["ts_code"] == code, "limit_up"].tolist()
        count = 0
        for flag in reversed(flags):
            if flag:
                count += 1
            else:
                break
        return count

    def prior_consecutive_limits(code):
        flags = hist.loc[
            (hist["ts_code"] == code) & (hist["trade_date"] <= prev_date), "limit_up"
        ].tolist()
        count = 0
        for flag in reversed(flags):
            if flag:
                count += 1
            else:
                break
        return count

    today["consec_limit"] = today["ts_code"].map(consecutive_limits)
    today["prior_consec_limit"] = today["ts_code"].map(prior_consecutive_limits)
    today["qualified_leader"] = (today["ret10"] >= 50) | (today["consec_limit"] >= 6) | (
        today["prev_limit"].fillna(False)
        & ((today["ret10"] >= 50) | (today["prior_consec_limit"] >= 6))
    )
    today["break_trigger"] = today["qualified_leader"] & today["prev_limit"].fillna(False) & ~today["limit_up"]

    clean = today[
        ~today["name"].fillna("").str.contains("ST|退", case=False, regex=True)
    ].copy()
    limits = clean[clean["limit_up"]].copy()
    emotional = limits[
        clean.loc[limits.index, "total_mv_yi"].between(50, 300)
        & clean.loc[limits.index, "turnover_rate"].between(5, 15)
    ].copy()
    new_high = clean[
        (clean["close"] >= clean["high10"] * 0.995)
        & (clean["close"] > clean["ma10"])
        & (clean["amount_yi"] >= 5)
    ].copy()
    leaders = clean[clean["qualified_leader"]].copy()
    breaks = clean[clean["break_trigger"]].copy()

    cols = [
        "ts_code", "name", "industry", "market", "close", "pct_chg", "amount_yi",
        "turnover_rate", "volume_ratio", "total_mv_yi", "pe_ttm", "ma5", "ma10",
        "ret10", "consec_limit", "prior_consec_limit",
        "prev_limit", "limit_up",
    ]
    out = {
        "trade_dates": [prev_date, today_date],
        "breadth": {
            "up": int((today["pct_chg"] > 0).sum()),
            "down": int((today["pct_chg"] < 0).sum()),
            "flat": int((today["pct_chg"] == 0).sum()),
            "amount_yi": round(float(today["amount"].sum() / 100000), 1),
            "limit_up": int(limits.shape[0]),
            "up5": int((clean["pct_chg"] >= 5).sum()),
            "down5": int((clean["pct_chg"] <= -5).sum()),
        },
        "limit_industries": limits.groupby("industry").size().sort_values(
            ascending=False
        ).head(20).to_dict(),
        "emotional_candidates": emotional.sort_values(
            ["consec_limit", "amount"], ascending=False
        )[cols].to_dict("records"),
        "qualified_leaders": leaders.sort_values(
            ["ret10", "consec_limit"], ascending=False
        )[cols].head(30).to_dict("records"),
        "break_triggers": breaks.sort_values("amount", ascending=False)[cols].to_dict("records"),
        "trend_new_highs": new_high.sort_values(
            ["ret10", "amount"], ascending=False
        )[cols].head(40).to_dict("records"),
        "top_limits": limits.sort_values("amount", ascending=False)[cols].head(40).to_dict("records"),
        "resilient": clean[
            (clean["pct_chg"] >= 2) & (clean["amount_yi"] >= 5) & ~clean["limit_up"]
        ].sort_values(["pct_chg", "amount"], ascending=False)[cols].head(40).to_dict("records"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=lambda x: None if pd.isna(x) else x))


if __name__ == "__main__":
    main()
