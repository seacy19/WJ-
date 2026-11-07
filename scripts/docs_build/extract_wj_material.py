import json
import re
from collections import Counter
from pathlib import Path

from docx import Document


ROOT = Path(r"D:\HuaweiMoveData\Users\seacy\Documents\WJ策略")
DOCX = Path(r"D:\claude\WJ策略_完整版.docx")
LOG_DIR = Path(r"C:\Users\seacy\.claude\projects\D--claude")

AFTER_FILES = [
    "71cea434-2de8-4fa6-8e2b-5ab84caec309.jsonl",
    "05cc7ba6-6289-4ce7-88cc-9cd4f5dc0c04.jsonl",
    "ffacc8ae-8d79-4281-9569-5c7f019e0154.jsonl",
    "0bc5dcaf-4eb6-4359-9892-04dafd8aba06.jsonl",
    "5079351b-2a53-406a-869b-acfc738deae7.jsonl",
    "abe19f65-b7c7-4c53-9835-b733cd443368.jsonl",
    "c89eb02c-6d4e-4490-a75e-69aa9ad0b2c9.jsonl",
    "c565c6fe-7182-43cc-8b4b-bf26a0c60de9.jsonl",
    "6d35d8f2-a3f6-44c7-ad5b-621ce2ce706d.jsonl",
    "d58bcd67-8c2b-4c2c-a4d1-703602b10b9c.jsonl",
    "e9249369-4d94-48e7-8bdd-943842125670.jsonl",
    "f942b678-1002-4d76-8f30-0984ecfd5591.jsonl",
    "c3c4f475-dfe5-4676-b7af-366f1ead18cb.jsonl",
    "356be905-292b-491d-a940-b4accd059224.jsonl",
    "d62316d2-380e-4b85-b003-a9c866301de8.jsonl",
    "fb9e99ea-aaee-4f30-ac3d-acc7edcf1193.jsonl",
    "54b8dc4f-ec00-41fd-af7d-1dfba8473322.jsonl",
    "ee63adfe-5c1b-4440-bccc-98a518f91912.jsonl",
    "36513c51-8ea5-45de-98b8-3c88fadd3f2e.jsonl",
    "27e07e2f-ca6a-4cf2-92e0-1de8bca50d25.jsonl",
    "cc360b0a-52a1-45be-8896-7421c7f185af.jsonl",
    "de3b154a-816c-411a-84bb-9211b2cb1698.jsonl",
    "33b0a301-ed37-4602-9c2c-bca6abddc15b.jsonl",
    "73363b88-d28e-4ab0-a8cb-6f6a9283e80e.jsonl",
    "2bf33c54-a3c0-4ad9-8b5a-89ac786bd84b.jsonl",
    "efec96ee-1040-4eb7-b09b-9ef4f44b941b.jsonl",
    "424fd10f-bc04-4e0c-88cb-364434ba5dfd.jsonl",
    "73227bbf-7647-4520-8d3a-aa3df11fc73c.jsonl",
    "046fc472-e9bf-48f0-9305-640be72d810c.jsonl",
    "f794d78c-69f1-498e-ba1d-4bb608aaf50a.jsonl",
    "1c35d0e5-4679-42ab-b85e-048366034f04.jsonl",
    "b8eab7de-cce3-45c7-9e25-a701746609f6.jsonl",
    "426bc54b-f22c-459c-af50-3a9d2269b665.jsonl",
    "0f6aae03-9cce-452b-83ca-8b481346f491.jsonl",
    "cf45452e-8666-4bb1-b0e4-e79bb65f0492.jsonl",
    "e98365ef-f034-43d4-b4cc-208702455f53.jsonl",
    "2d9447fa-d884-448a-b45c-1355edf025a9.jsonl",
    "03550884-bb0c-468d-9012-5f351f4fbee5.jsonl",
    "7418e4b4-7db3-45f8-9d57-0d044a8b0067.jsonl",
    "db585761-9891-4217-a98a-32df7a872b14.jsonl",
    "730137e3-ad9a-4f94-b170-bc123a3fc9aa.jsonl",
    "9979d869-c80d-42ac-8f70-35ce76afabba.jsonl",
    "eca6bdd9-740f-4fe1-9381-5b26fcd7d4d9.jsonl",
    "e715a14b-83e3-4670-8a47-658274ee336c.jsonl",
    "9a1ab15c-4064-4188-8611-6e4e407ea7b0.jsonl",
]

NOISE_RE = re.compile(
    r"(bash|powershell|python|Traceback|File \"|Exit code|npm|pip|git |ls |cat |sed |grep |rg |SELECT |CREATE TABLE|INSERT INTO|"
    r"已读取|正在读取|工具|TodoWrite|Task\(|Bash\(|Read\(|Edit\(|Write\(|MultiEdit\(|Glob\(|Grep\(|LS\(|Notebook|"
    r"⎿|```(?:json|bash|python|sql)|<function_calls>|<tool_result>)",
    re.I,
)

KEY_RE = re.compile(
    r"(WJ|策略|选股|筛选|涨停|连板|首板|二板|竞价|集合竞价|打板|炸板|分歧|一致|情绪|周期|题材|"
    r"龙头|容量|风险|仓位|买点|卖点|止损|止盈|复盘|明日|模型|评分|因子|阈值|规则|优化|完整版|最终|总结)"
)


def text_from_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif "text" in item and isinstance(item["text"], str):
                    parts.append(item["text"])
        return "\n".join(parts)
    if isinstance(content, dict):
        return text_from_content(content.get("content") or content.get("text"))
    return ""


def msg_text(obj):
    if obj.get("type") in {"custom-title", "ai-title"}:
        return obj.get("customTitle") or obj.get("aiTitle") or ""
    msg = obj.get("message")
    if isinstance(msg, dict):
        return text_from_content(msg.get("content"))
    return text_from_content(obj.get("content"))


def clean_text(s):
    s = s.replace("\r\n", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def score(text):
    t = clean_text(text)
    if len(t) < 80:
        return 0
    if NOISE_RE.search(t[:2000]) and len(KEY_RE.findall(t)) < 6:
        return 0
    hits = len(KEY_RE.findall(t))
    headings = len(re.findall(r"^#{1,4}\s+|^\d+[\.、]|^[-*]\s+", t, re.M))
    zh = len(re.findall(r"[\u4e00-\u9fff]", t))
    return hits * 8 + headings * 3 + min(zh // 120, 80) - min(len(t) // 25000, 20)


def extract_docx():
    doc = Document(DOCX)
    lines = []
    for i, p in enumerate(doc.paragraphs):
        text = clean_text(p.text)
        if text:
            lines.append(f"{i:03d}\t{p.style.name}\t{text}")
    for ti, table in enumerate(doc.tables):
        lines.append(f"\n[TABLE {ti}]")
        for row in table.rows:
            cells = [clean_text(c.text) for c in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    (ROOT / "original_docx_extract.txt").write_text("\n".join(lines), encoding="utf-8")


def extract_logs():
    candidates = []
    per_file = []
    role_counter = Counter()
    for name in AFTER_FILES:
        path = LOG_DIR / name
        if not path.exists():
            continue
        local = []
        for idx, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            role = obj.get("message", {}).get("role") if isinstance(obj.get("message"), dict) else obj.get("type", "")
            role_counter[str(role)] += 1
            text = clean_text(msg_text(obj))
            if not text:
                continue
            sc = score(text)
            if sc <= 0:
                continue
            rec = {
                "file": name,
                "line": idx + 1,
                "role": role,
                "score": sc,
                "chars": len(text),
                "text": text,
            }
            candidates.append(rec)
            local.append(rec)
        per_file.append((name, len(local), sum(r["chars"] for r in local), max([r["score"] for r in local], default=0)))

    candidates.sort(key=lambda r: (r["score"], r["chars"]), reverse=True)
    top = candidates[:140]

    summary_lines = [
        "# Claude Code 6.20 后高信号材料索引",
        "",
        f"候选片段数: {len(candidates)}",
        f"纳入详读片段数: {len(top)}",
        f"角色统计: {dict(role_counter)}",
        "",
        "## 分文件统计",
    ]
    for name, count, chars, max_score in per_file:
        summary_lines.append(f"- {name}: {count} 段, {chars} 字符, max_score={max_score}")
    summary_lines.append("\n## Top 片段")
    for i, rec in enumerate(top, 1):
        excerpt = rec["text"]
        if len(excerpt) > 9000:
            excerpt = excerpt[:9000] + "\n...[截断]"
        summary_lines.append(
            f"\n### {i}. {rec['file']}:{rec['line']} role={rec['role']} score={rec['score']} chars={rec['chars']}\n\n{excerpt}\n"
        )
    (ROOT / "post_620_high_signal.md").write_text("\n".join(summary_lines), encoding="utf-8")


if __name__ == "__main__":
    extract_docx()
    extract_logs()
