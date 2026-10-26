import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import tushare as ts
from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "tushare_cache.sqlite"
DEFAULT_SECRET_FILE = Path(__file__).resolve().parent / "market_data_mcp_secrets.bin"
DEFAULT_PLAINTEXT_SECRET_FILE = Path(__file__).resolve().parent / ".market_data_mcp_secrets.json"

mcp = FastMCP("tushare-a-share")


def _db_path() -> Path:
    path = Path(os.environ.get("TUSHARE_CACHE_DB", str(DEFAULT_DB)))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_cache (
            cache_key TEXT PRIMARY KEY,
            api_name TEXT NOT NULL,
            params_json TEXT NOT NULL,
            fields TEXT,
            fetched_at TEXT NOT NULL,
            rows_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT NOT NULL,
            params_json TEXT NOT NULL,
            fields TEXT,
            source TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    return conn


def _token() -> str:
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
    if not token:
        token = _load_secret("TUSHARE_TOKEN") or _load_secret("TUSHARE_PRO_TOKEN")
    if not token:
        token = _load_plaintext_secret("TUSHARE_TOKEN") or _load_plaintext_secret("TUSHARE_PRO_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set. Set it in the MCP environment or encrypted MCP secret file.")
    return token


def _secret_file() -> Path:
    return Path(os.environ.get("MARKET_DATA_MCP_SECRET_FILE", str(DEFAULT_SECRET_FILE)))


def _load_secret(name: str) -> str | None:
    path = _secret_file()
    if not path.exists():
        return None
    try:
        import win32crypt

        encrypted = path.read_bytes()
        _desc, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
        data = json.loads(decrypted.decode("utf-8"))
        value = data.get(name)
        return value if isinstance(value, str) and value else None
    except Exception:
        return None


def _load_plaintext_secret(name: str) -> str | None:
    path = Path(os.environ.get("MARKET_DATA_MCP_PLAINTEXT_SECRET_FILE", str(DEFAULT_PLAINTEXT_SECRET_FILE)))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get(name)
        return value if isinstance(value, str) and value else None
    except Exception:
        return None


def _cache_key(api_name: str, params: dict[str, Any], fields: str | None) -> str:
    payload = json.dumps(
        {"api_name": api_name, "params": params, "fields": fields or ""},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _df_to_rows(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit and limit > 0:
        df = df.head(limit)
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def _query(api_name: str, params: dict[str, Any], fields: str | None, limit: int | None, use_cache: bool) -> dict[str, Any]:
    key = _cache_key(api_name, params, fields)
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()

    if use_cache:
        row = conn.execute(
            "SELECT fetched_at, rows_json FROM api_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row:
            rows = json.loads(row[1])
            visible_rows = rows[:limit] if limit and limit > 0 else rows
            conn.execute(
                "INSERT INTO api_calls(api_name, params_json, fields, source, row_count, fetched_at) VALUES(?,?,?,?,?,?)",
                (api_name, json.dumps(params, ensure_ascii=False, sort_keys=True), fields, "cache", len(rows), now),
            )
            conn.commit()
            return {
                "source": "cache",
                "api_name": api_name,
                "params": params,
                "fields": fields,
                "row_count": len(rows),
                "returned_count": len(visible_rows),
                "fetched_at": row[0],
                "rows": visible_rows,
            }

    pro = ts.pro_api(_token())
    fn = getattr(pro, api_name, None)
    if fn is None:
        # TuShare Pro also exposes a generic query interface.
        df = pro.query(api_name, **params, fields=fields)
    else:
        call_params = dict(params)
        if fields:
            call_params["fields"] = fields
        df = fn(**call_params)

    rows = _df_to_rows(df)
    conn.execute(
        "REPLACE INTO api_cache(cache_key, api_name, params_json, fields, fetched_at, rows_json) VALUES(?,?,?,?,?,?)",
        (key, api_name, json.dumps(params, ensure_ascii=False, sort_keys=True), fields, now, json.dumps(rows, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO api_calls(api_name, params_json, fields, source, row_count, fetched_at) VALUES(?,?,?,?,?,?)",
        (api_name, json.dumps(params, ensure_ascii=False, sort_keys=True), fields, "tushare", len(rows), now),
    )
    conn.commit()
    visible_rows = rows[:limit] if limit and limit > 0 else rows
    return {
        "source": "tushare",
        "api_name": api_name,
        "params": params,
        "fields": fields,
        "row_count": len(rows),
        "returned_count": len(visible_rows),
        "fetched_at": now,
        "rows": visible_rows,
    }


@mcp.tool()
def query_api(api_name: str, params_json: str = "{}", fields: str = "", limit: int = 200, use_cache: bool = True) -> str:
    """Call any TuShare Pro API by name. params_json must be a JSON object string."""
    params = json.loads(params_json or "{}")
    if not isinstance(params, dict):
        raise ValueError("params_json must decode to a JSON object.")
    result = _query(api_name, params, fields or None, limit, use_cache)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def stock_basic(exchange: str = "", list_status: str = "L", limit: int = 500, use_cache: bool = True) -> str:
    """List A-share basic stock metadata, including ts_code, name, area, industry, market and list_date."""
    fields = "ts_code,symbol,name,area,industry,market,list_date"
    return query_api("stock_basic", json.dumps({"exchange": exchange, "list_status": list_status}, ensure_ascii=False), fields, limit, use_cache)


@mcp.tool()
def daily(ts_code: str, start_date: str, end_date: str, limit: int = 500, use_cache: bool = True) -> str:
    """Fetch daily OHLCV bars. Dates use YYYYMMDD."""
    fields = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
    return query_api(
        "daily",
        json.dumps({"ts_code": ts_code, "start_date": start_date, "end_date": end_date}, ensure_ascii=False),
        fields,
        limit,
        use_cache,
    )


@mcp.tool()
def daily_basic(ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "", limit: int = 500, use_cache: bool = True) -> str:
    """Fetch valuation and turnover fields such as total market value, PE/PB and turnover."""
    params = {k: v for k, v in {"ts_code": ts_code, "trade_date": trade_date, "start_date": start_date, "end_date": end_date}.items() if v}
    fields = "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pb,total_mv,circ_mv"
    return query_api("daily_basic", json.dumps(params, ensure_ascii=False), fields, limit, use_cache)


@mcp.tool()
def financial_indicator(ts_code: str, start_date: str = "", end_date: str = "", period: str = "", limit: int = 200, use_cache: bool = True) -> str:
    """Fetch financial indicators for WJ fundamental leader checks: ROE, gross margin, net profit growth, debt ratio, cash flow ratios."""
    params = {k: v for k, v in {"ts_code": ts_code, "start_date": start_date, "end_date": end_date, "period": period}.items() if v}
    fields = "ts_code,ann_date,end_date,roe,grossprofit_margin,netprofit_margin,netprofit_yoy,or_yoy,debt_to_assets,ocf_to_profit"
    return query_api("fina_indicator", json.dumps(params, ensure_ascii=False), fields, limit, use_cache)


@mcp.tool()
def limit_list_d(trade_date: str = "", ts_code: str = "", limit_type: str = "", limit: int = 1000, use_cache: bool = True) -> str:
    """Fetch daily up/down limit list when the TuShare account has permission. Use for涨停数、连板/情绪 checks."""
    params = {k: v for k, v in {"trade_date": trade_date, "ts_code": ts_code, "limit_type": limit_type}.items() if v}
    fields = "trade_date,ts_code,name,industry,close,pct_chg,amount,limit_amount,fd_amount,first_time,last_time,open_times,up_stat,limit_times"
    return query_api("limit_list_d", json.dumps(params, ensure_ascii=False), fields, limit, use_cache)


@mcp.tool()
def cache_stats() -> str:
    """Return local SQLite cache location and API call statistics."""
    conn = _connect()
    cache_rows = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
    calls = conn.execute("SELECT source, COUNT(*), SUM(row_count) FROM api_calls GROUP BY source").fetchall()
    recent = conn.execute(
        "SELECT api_name, source, row_count, fetched_at FROM api_calls ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return json.dumps(
        {
            "cache_db": str(_db_path()),
            "cache_entries": cache_rows,
            "calls_by_source": [{"source": r[0], "calls": r[1], "rows": r[2] or 0} for r in calls],
            "recent_calls": [
                {"api_name": r[0], "source": r[1], "row_count": r[2], "fetched_at": r[3]} for r in recent
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def token_diagnostics() -> str:
    """Diagnose token sources without returning secret values."""
    plain_path = Path(os.environ.get("MARKET_DATA_MCP_PLAINTEXT_SECRET_FILE", str(DEFAULT_PLAINTEXT_SECRET_FILE)))
    plain_keys: list[str] = []
    plain_read_error = ""
    if plain_path.exists():
        try:
            data = json.loads(plain_path.read_text(encoding="utf-8"))
            plain_keys = sorted([k for k, v in data.items() if isinstance(v, str) and v])
        except Exception as exc:
            plain_read_error = f"{type(exc).__name__}: {exc}"
    dpapi_path = _secret_file()
    dpapi_keys: list[str] = []
    dpapi_read_error = ""
    if dpapi_path.exists():
        try:
            import win32crypt

            encrypted = dpapi_path.read_bytes()
            _desc, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
            data = json.loads(decrypted.decode("utf-8"))
            dpapi_keys = sorted([k for k, v in data.items() if isinstance(v, str) and v])
        except Exception as exc:
            dpapi_read_error = f"{type(exc).__name__}: {exc}"
    return json.dumps(
        {
            "token_function_available": _token_available(),
            "env": {
                "TUSHARE_TOKEN": bool(os.environ.get("TUSHARE_TOKEN")),
                "TUSHARE_PRO_TOKEN": bool(os.environ.get("TUSHARE_PRO_TOKEN")),
                "IFIND_API_KEY": bool(os.environ.get("IFIND_API_KEY")),
                "MARKET_DATA_MCP_PLAINTEXT_SECRET_FILE": os.environ.get("MARKET_DATA_MCP_PLAINTEXT_SECRET_FILE", ""),
            },
            "plain": {
                "path": str(plain_path),
                "exists": plain_path.exists(),
                "keys": plain_keys,
                "error": plain_read_error,
            },
            "dpapi": {
                "path": str(dpapi_path),
                "exists": dpapi_path.exists(),
                "keys": dpapi_keys,
                "error": dpapi_read_error,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def _token_available() -> bool:
    try:
        return bool(_token())
    except Exception:
        return False


if __name__ == "__main__":
    if "--self-test" in os.sys.argv:
        print(json.dumps({
            "server": "tushare-a-share",
            "db": str(_db_path()),
            "secret_file": str(_secret_file()),
            "plaintext_secret_file": str(DEFAULT_PLAINTEXT_SECRET_FILE),
            "token_set": bool(
                os.environ.get("TUSHARE_TOKEN")
                or os.environ.get("TUSHARE_PRO_TOKEN")
                or _load_secret("TUSHARE_TOKEN")
                or _load_secret("TUSHARE_PRO_TOKEN")
                or _load_plaintext_secret("TUSHARE_TOKEN")
                or _load_plaintext_secret("TUSHARE_PRO_TOKEN")
            ),
        }, ensure_ascii=False))
    else:
        mcp.run()
