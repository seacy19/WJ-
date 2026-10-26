import json
import sqlite3
from collections import defaultdict
from pathlib import Path


CACHE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\data\tushare_cache.sqlite"
)
END_DATE = "20260721"


def load_latest(conn, api_name, params_like=None):
    sql = """
        SELECT rows_json
        FROM api_cache
        WHERE api_name = ?
    """
    params = [api_name]
    if params_like:
        sql += " AND params_json LIKE ?"
        params.append(params_like)
    sql += " ORDER BY fetched_at DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    return json.loads(row[0]) if row else []


def is_limit_up(row, name):
    pct = float(row.get("pct_chg") or 0)
    code = row["ts_code"]
    upper_name = (name or "").upper()
    if "ST" in upper_name:
        return pct >= 4.8
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.endswith(".BJ"):
        return pct >= 29.5
    return pct >= 9.5


def main():
    conn = sqlite3.connect(CACHE)
    cache_rows = conn.execute(
        """
        SELECT params_json, rows_json, fetched_at
        FROM api_cache
        WHERE api_name = 'daily'
          AND params_json LIKE '%trade_date%'
        ORDER BY fetched_at DESC
        """
    ).fetchall()

    by_date = {}
    for params_json, rows_json, _ in cache_rows:
        params = json.loads(params_json)
        date = params.get("trade_date")
        if date and date <= END_DATE and date not in by_date:
            rows = json.loads(rows_json)
            if len(rows) > 5000 and rows and "vol" in rows[0] and "amount" in rows[0]:
                by_date[date] = rows

    dates = sorted(by_date)[-21:]
    basics = {}
    basic_cache_rows = conn.execute(
        """
        SELECT rows_json
        FROM api_cache
        WHERE api_name = 'daily_basic'
          AND params_json LIKE ?
        ORDER BY fetched_at DESC
        """,
        (f"%{END_DATE}%",),
    ).fetchall()
    for (rows_json,) in basic_cache_rows:
        for row in json.loads(rows_json):
            if row.get("trade_date") == END_DATE:
                basics.setdefault(row["ts_code"], row)
    stocks = {
        row["ts_code"]: row
        for row in load_latest(conn, "stock_basic")
    }

    histories = defaultdict(list)
    for date in dates:
        for row in by_date[date]:
            histories[row["ts_code"]].append(row)

    today = []
    for code, hist in histories.items():
        hist.sort(key=lambda x: x["trade_date"])
        if hist[-1]["trade_date"] != END_DATE:
            continue
        stock = stocks.get(code, {})
        name = stock.get("name", "")
        if "ST" in name.upper() or "退" in name:
            continue
        row = dict(hist[-1])
        row.update(
            name=name,
            industry=stock.get("industry"),
            market=stock.get("market"),
        )
        basic = basics.get(code, {})
        row.update(
            turnover_rate=basic.get("turnover_rate"),
            volume_ratio=basic.get("volume_ratio"),
            total_mv_yi=(basic.get("total_mv") or 0) / 10000,
            pe=basic.get("pe"),
            pb=basic.get("pb"),
        )
        closes = [float(x["close"]) for x in hist]
        vols = [float(x["vol"]) for x in hist]
        highs = [float(x["high"]) for x in hist]
        row["ma5"] = sum(closes[-5:]) / min(5, len(closes))
        row["ma10"] = sum(closes[-10:]) / min(10, len(closes))
        row["ma20"] = sum(closes[-20:]) / min(20, len(closes))
        row["vol_ma5"] = sum(vols[-6:-1]) / max(1, len(vols[-6:-1]))
        row["vol_multiple"] = vols[-1] / row["vol_ma5"] if row["vol_ma5"] else None
        row["high10"] = max(highs[-10:])
        row["high20"] = max(highs[-20:])
        row["low20"] = min(float(x["low"]) for x in hist[-20:])
        row["ret10"] = (
            (closes[-1] / closes[-11] - 1) * 100 if len(closes) >= 11 else None
        )
        row["ret20"] = (
            (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else None
        )
        flags = [is_limit_up(x, name) for x in hist]
        row["limit_up"] = flags[-1]
        row["prev_limit"] = flags[-2] if len(flags) >= 2 else False
        count = 0
        for flag in reversed(flags):
            if not flag:
                break
            count += 1
        row["consec_limit"] = count
        prior_count = 0
        for flag in reversed(flags[:-1]):
            if not flag:
                break
            prior_count += 1
        row["prior_consec_limit"] = prior_count
        row["qualified_leader"] = (
            (row["ret10"] is not None and row["ret10"] >= 50)
            or row["consec_limit"] >= 6
            or (row["prev_limit"] and prior_count >= 6)
        )
        row["break_trigger"] = (
            row["qualified_leader"] and row["prev_limit"] and not row["limit_up"]
        )
        row["amount_yi"] = float(row["amount"]) / 100000
        today.append(row)

    cols = [
        "ts_code", "name", "industry", "close", "pct_chg", "amount_yi",
        "turnover_rate", "volume_ratio", "vol_multiple", "total_mv_yi",
        "pe", "pb", "ma5", "ma10", "ma20", "high20", "low20",
        "ret10", "ret20", "consec_limit",
        "prior_consec_limit", "prev_limit", "limit_up",
    ]

    def select(predicate, sort_key, reverse=True, limit=15):
        rows = [x for x in today if predicate(x)]
        rows.sort(key=sort_key, reverse=reverse)
        return [{k: x.get(k) for k in cols} for x in rows[:limit]]

    limits = [x for x in today if x["limit_up"]]
    industries = defaultdict(int)
    for row in limits:
        industries[row.get("industry") or "未知"] += 1

    output = {
        "dates": dates,
        "breadth": {
            "up": sum(x["pct_chg"] > 0 for x in today),
            "down": sum(x["pct_chg"] < 0 for x in today),
            "flat": sum(x["pct_chg"] == 0 for x in today),
            "amount_yi": round(sum(x["amount_yi"] for x in today), 1),
            "limit_up": len(limits),
            "up5": sum(x["pct_chg"] >= 5 for x in today),
            "down5": sum(x["pct_chg"] <= -5 for x in today),
        },
        "limit_industries": dict(
            sorted(industries.items(), key=lambda x: x[1], reverse=True)
        ),
        "qualified_leaders": select(
            lambda x: x["qualified_leader"],
            lambda x: (x["ret10"] or -999, x["consec_limit"]),
        ),
        "break_triggers": select(
            lambda x: x["break_trigger"],
            lambda x: x["amount_yi"],
        ),
        "top_limits": select(
            lambda x: x["limit_up"],
            lambda x: x["amount_yi"],
        ),
        "resilient": select(
            lambda x: 2 <= x["pct_chg"] < 9.5 and x["amount_yi"] >= 5,
            lambda x: (x["pct_chg"], x["amount_yi"]),
        ),
        "low_volume_candidates": select(
            lambda x: (
                -2 <= x["pct_chg"] <= 2
                and x["amount_yi"] >= 1
                and (x["volume_ratio"] or 0) >= 1.3
                and 20 <= x["total_mv_yi"] <= 150
                and (x["ret10"] is None or x["ret10"] <= 20)
                and x["close"] >= x["ma5"] * 0.98
            ),
            lambda x: (
                x["volume_ratio"] or 0,
                x["vol_multiple"] or 0,
                x["amount_yi"],
            ),
        ),
        "near_highs": select(
            lambda x: (
                x["close"] >= x["high10"] * 0.985
                and x["close"] >= x["ma10"]
                and x["amount_yi"] >= 5
                and not x["limit_up"]
            ),
            lambda x: (x["ret10"] or -999, x["amount_yi"]),
        ),
        "large_cap_700_1300": select(
            lambda x: (
                700 <= x["total_mv_yi"] <= 1300
                and x["amount_yi"] >= 5
            ),
            lambda x: (
                x["close"] / x["ma20"] if x["ma20"] else 0,
                x["amount_yi"],
            ),
            limit=80,
        ),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
