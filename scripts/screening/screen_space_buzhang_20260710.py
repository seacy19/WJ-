import json
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a"
    r"\market_data_mcp\.market_data_mcp_secrets.json"
)
OUT = Path(r"D:\HuaweiMoveData\Users\seacy\Documents\WJ策略\WJ策略_20260710_航天卫星补涨筛选.csv")


def token():
    data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    return data.get("TUSHARE_TOKEN") or data.get("TUSHARE_PRO_TOKEN")


def main():
    pro = ts.pro_api(token())
    end = "20260710"
    start = "20260601"
    fields_stock = "ts_code,symbol,name,area,industry,market,list_date"
    fields_daily = "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,amount"
    fields_basic = "ts_code,trade_date,turnover_rate,volume_ratio,total_mv"
    fields_limit = "trade_date,ts_code,up_limit,down_limit"

    stocks = pro.stock_basic(exchange="", list_status="L", fields=fields_stock)
    name_pats = [
        "航天", "卫星", "卫通", "火箭", "星网", "中船", "北斗", "导航",
        "普天", "高德", "佳缘", "海兰信", "雷科", "合众", "华力创通",
    ]
    theme = stocks[
        stocks["name"].fillna("").apply(lambda x: any(p in x for p in name_pats))
        | stocks["industry"].fillna("").isin(["航空", "船舶", "通信设备", "电信运营"])
    ].copy()

    rows = []
    for code in theme["ts_code"].tolist():
        try:
            d = pro.daily(ts_code=code, start_date=start, end_date=end, fields=fields_daily)
            if d.empty:
                continue
            d = d.sort_values("trade_date")
            for col in ["close", "pct_chg", "amount"]:
                d[col] = pd.to_numeric(d[col], errors="coerce")
            latest = d.iloc[-1].to_dict()
            latest["pct_10d"] = (d.iloc[-1]["close"] / d.iloc[-11]["close"] - 1) * 100 if len(d) >= 11 else None
            latest["pct_20d"] = (d.iloc[-1]["close"] / d.iloc[-21]["close"] - 1) * 100 if len(d) >= 21 else None
            rows.append(latest)
        except Exception:
            continue

    daily = pd.DataFrame(rows)
    basic = pro.daily_basic(trade_date=end, fields=fields_basic)
    limits = pro.stk_limit(trade_date=end, fields=fields_limit)
    for df in (basic, limits):
        for c in ["turnover_rate", "volume_ratio", "total_mv", "up_limit"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    x = (
        daily.merge(theme, on="ts_code", how="left")
        .merge(basic, on=["ts_code", "trade_date"], how="left")
        .merge(limits, on=["ts_code", "trade_date"], how="left")
    )
    x["amount_yi"] = x["amount"] / 100000
    x["total_mv_yi"] = x["total_mv"] / 10000
    x["is_limit_up"] = x["up_limit"].notna() & (x["close"] >= x["up_limit"] * 0.999) & (x["pct_chg"] > 0)
    x["buzhang_like"] = (
        x["pct_20d"].notna()
        & (x["pct_20d"] <= 20)
        & (x["total_mv_yi"] <= 100)
        & (x["volume_ratio"].fillna(0) >= 1.3)
        & (~x["is_limit_up"])
    )
    cols = [
        "ts_code", "name", "industry", "market", "close", "pct_chg", "pct_10d", "pct_20d",
        "amount_yi", "total_mv_yi", "turnover_rate", "volume_ratio", "is_limit_up", "buzhang_like",
    ]
    x = x[cols].sort_values(["buzhang_like", "volume_ratio", "amount_yi"], ascending=False)
    OUT.write_text(x.to_csv(index=False), encoding="utf-8-sig")
    print(x[x["buzhang_like"]].head(30).to_string(index=False))
    print("OUT", OUT)


if __name__ == "__main__":
    main()
