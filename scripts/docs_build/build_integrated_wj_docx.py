import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(r"D:\HuaweiMoveData\Users\seacy\Documents\WJ策略")
MD = ROOT / "latest_wj_strategy_from_logs.md"
OUT = ROOT / "WJ策略_整合版_2026-06-30.docx"


FONT_CJK = "Microsoft YaHei"
FONT_LATIN = "Calibri"
ACCENT = RGBColor(31, 77, 120)
ACCENT2 = RGBColor(46, 116, 181)
MUTED = RGBColor(89, 89, 89)
FILL = "E8EEF5"
FILL_LIGHT = "F4F6F9"
BORDER = "D9E2F3"


def set_run_font(run, name=FONT_CJK, size=None, bold=None, color=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), FONT_LATIN)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), FONT_LATIN)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = color


def set_style_font(style, size, color=None, bold=None, after=6, before=0, line=1.25):
    style.font.name = FONT_CJK
    style._element.rPr.rFonts.set(qn("w:ascii"), FONT_LATIN)
    style._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_LATIN)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
    style.font.size = Pt(size)
    if color:
        style.font.color.rgb = color
    if bold is not None:
        style.font.bold = bold
    pf = style.paragraph_format
    pf.space_after = Pt(after)
    pf.space_before = Pt(before)
    pf.line_spacing = line


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, v in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table, color=BORDER):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        elem = borders.find(qn(f"w:{edge}"))
        if elem is None:
            elem = OxmlElement(f"w:{edge}")
            borders.append(elem)
        elem.set(qn("w:val"), "single")
        elem.set(qn("w:sz"), "4")
        elem.set(qn("w:space"), "0")
        elem.set(qn("w:color"), color)


def set_table_width(table, width_dxa=9360):
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(width_dxa))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_layout = tbl_pr.first_child_found_in("w:tblLayout")
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")


def add_markdown_runs(paragraph, text, base_size=10.5, color=None):
    text = text.replace("**", "\x02")
    parts = re.split(r"(\x02)", text)
    bold = False
    for part in parts:
        if part == "\x02":
            bold = not bold
            continue
        if not part:
            continue
        # Split inline code, keeping delimiters.
        sub = re.split(r"(`[^`]+`)", part)
        for seg in sub:
            if not seg:
                continue
            run = paragraph.add_run(seg[1:-1] if seg.startswith("`") and seg.endswith("`") else seg)
            set_run_font(run, size=base_size, bold=bold, color=color)
            if seg.startswith("`") and seg.endswith("`"):
                run.font.name = "Consolas"
                run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Consolas")
                run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Consolas")
                run.font.size = Pt(base_size - 0.5)


def clean_inline(text):
    return re.sub(r"\s+", " ", text.strip())


def parse_table(lines, start):
    table_lines = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
        table_lines.append(lines[i].strip())
        i += 1
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells):
            continue
        rows.append(cells)
    return rows, i


def add_table(doc, rows):
    if not rows:
        return
    cols = max(len(r) for r in rows)
    rows = [r + [""] * (cols - len(r)) for r in rows]
    table = doc.add_table(rows=len(rows), cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_width(table)
    set_table_borders(table)
    for ri, row in enumerate(table.rows):
        for ci, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            if ri == 0:
                set_cell_shading(cell, FILL)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.15
                add_markdown_runs(p, rows[ri][ci], base_size=9.2, color=ACCENT if ri == 0 else None)
                if ri == 0:
                    for run in p.runs:
                        run.bold = True
                if len(rows[ri][ci]) < 12:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()


def add_callout(doc, text, fill=FILL_LIGHT):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_width(table)
    set_table_borders(table, "D0D7E2")
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    set_cell_margins(cell, top=120, bottom=120, start=160, end=160)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.18
    add_markdown_runs(p, text, base_size=10)
    doc.add_paragraph()


def add_code_block(doc, lines):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_width(table)
    set_table_borders(table, "DADCE0")
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F7F7F7")
    set_cell_margins(cell, top=120, bottom=120, start=160, end=160)
    p = cell.paragraphs[0]
    for idx, line in enumerate(lines):
        if idx:
            p.add_run("\n")
        run = p.add_run(line)
        run.font.name = "Consolas"
        run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Consolas")
        run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Consolas")
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT_CJK)
        run.font.size = Pt(8.5)
    doc.add_paragraph()


def build():
    text = MD.read_text(encoding="utf-8")
    text = re.sub(r"^Base directory.*?\n\n", "", text, flags=re.S)
    lines = text.splitlines()

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = doc.styles
    set_style_font(styles["Normal"], 10.5, after=6, line=1.25)
    set_style_font(styles["Heading 1"], 16, color=ACCENT2, bold=True, before=18, after=10)
    set_style_font(styles["Heading 2"], 13, color=ACCENT2, bold=True, before=14, after=7)
    set_style_font(styles["Heading 3"], 12, color=ACCENT, bold=True, before=10, after=5)
    set_style_font(styles["List Bullet"], 10.5, after=4, line=1.25)
    set_style_font(styles["List Number"], 10.5, after=4, line=1.25)

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    run = title.add_run("WJ策略 —— A股选股框架")
    set_run_font(run, size=21, bold=True, color=ACCENT)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(10)
    add_markdown_runs(sub, "整合版：基于 2026-06-20 原始记录，并整合 2026-06-21 至 2026-06-30 Claude Code 优化记录。", 10, MUTED)

    add_callout(
        doc,
        "整合要点：保留原 WJ 策略主框架，纳入后续优化中的执行纪律、真实题材识别、基本面龙头分支、补涨级龙头门槛、日内买点、iFinD 取数映射与股票深挖框架。",
    )

    in_code = False
    code_lines = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                add_code_block(doc, code_lines)
                code_lines = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue
        if not line.strip() or line.strip() == "---":
            i += 1
            continue

        if line.strip().startswith("|") and line.strip().endswith("|"):
            rows, i = parse_table(lines, i)
            add_table(doc, rows)
            continue

        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            heading = clean_inline(m.group(2))
            if level == 1 and heading.startswith("WJ策略"):
                i += 1
                continue
            style = f"Heading {min(level, 3)}"
            p = doc.add_paragraph(style=style)
            add_markdown_runs(p, heading, base_size={2: 13, 3: 12}.get(level, 16), color=ACCENT2 if level <= 2 else ACCENT)
            i += 1
            continue

        if line.startswith(">"):
            block = [line.lstrip("> ").strip()]
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i].lstrip("> ").strip())
                i += 1
            add_callout(doc, " ".join([b for b in block if b and b != "---"]))
            continue

        if re.match(r"^\s*[-*]\s+", line):
            p = doc.add_paragraph(style="List Bullet")
            add_markdown_runs(p, re.sub(r"^\s*[-*]\s+", "", line), base_size=10.2)
            i += 1
            continue

        if re.match(r"^\s*\d+[.、]\s+", line):
            p = doc.add_paragraph(style="List Number")
            add_markdown_runs(p, re.sub(r"^\s*\d+[.、]\s+", "", line), base_size=10.2)
            i += 1
            continue

        p = doc.add_paragraph()
        add_markdown_runs(p, clean_inline(line), base_size=10.5)
        i += 1

    if code_lines:
        add_code_block(doc, code_lines)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_markdown_runs(footer, "WJ策略整合版 · 2026-06-30", 8.5, MUTED)

    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
