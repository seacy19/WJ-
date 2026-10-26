import json
import re
from pathlib import Path


ROOT = Path(r"D:\HuaweiMoveData\Users\seacy\Documents\WJ策略")
LOG = Path(r"C:\Users\seacy\.claude\projects\D--claude\9a1ab15c-4064-4188-8611-6e4e407ea7b0.jsonl")


def text_from_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    out.append(item.get("text", ""))
                elif isinstance(item.get("text"), str):
                    out.append(item["text"])
        return "\n".join(out)
    if isinstance(content, dict):
        return text_from_content(content.get("content") or content.get("text"))
    return ""


def msg_text(obj):
    msg = obj.get("message")
    if isinstance(msg, dict):
        return text_from_content(msg.get("content"))
    return text_from_content(obj.get("content"))


records = []
for i, line in enumerate(LOG.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
    try:
        obj = json.loads(line)
    except Exception:
        continue
    text = msg_text(obj)
    if "# WJ策略" in text and ("策略概览" in text or "策略概述" in text) and "## 输出格式规范" in text:
        records.append((i, obj.get("message", {}).get("role"), text))

if not records:
    records = []
    for i, line in enumerate(LOG.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        text = msg_text(obj)
        if "# WJ策略" in text and ("策略概览" in text or "策略概述" in text) and len(text) > 20000:
            records.append((i, obj.get("message", {}).get("role"), text))

if not records:
    raise SystemExit("No full WJ strategy record found")

line_no, role, text = records[-1]
start = text.find("# WJ策略")
text = text[start:].strip()

# Remove trailing non-document chatter after the last known formal section if present.
marker = "## 输出格式规范"
if marker in text:
    # Keep everything; this section is part of the strategy.
    pass

text = re.sub(r"\n{3,}", "\n\n", text)
out = ROOT / "latest_wj_strategy_from_logs.md"
out.write_text(text, encoding="utf-8")
(ROOT / "latest_wj_strategy_source.txt").write_text(
    f"source={LOG}\nline={line_no}\nrole={role}\nchars={len(text)}\n",
    encoding="utf-8",
)
print(out)
print(f"line={line_no} role={role} chars={len(text)}")
