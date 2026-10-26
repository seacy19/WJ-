import json
import os
from pathlib import Path

import win32crypt


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\market_data_mcp_secrets.bin"
)


def main():
    data = {
        key: value
        for key in ("TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN", "IFIND_API_KEY")
        if (value := os.environ.get(key))
    }
    if not data:
        raise SystemExit("No market data secrets found in current process environment.")
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = win32crypt.CryptProtectData(payload, "market-data-mcp", None, None, None, 0)
    SECRET_FILE.write_bytes(encrypted)
    print(json.dumps({"secret_file": str(SECRET_FILE), "keys": sorted(data.keys())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
