import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(r"D:\HuaweiMoveData\Users\seacy\Documents\WJ策略")
SRC = ROOT / "latest_wj_strategy_from_logs.md"
OUT_MD = ROOT / "WJ策略_v1.4_EXPMA整合完整版_红色标注.md"
OUT_DOCX = ROOT / "WJ策略_v1.4_EXPMA整合完整版_红色标注.docx"

FONT_CJK = "Microsoft YaHei"
FONT_LATIN = "Calibri"
ACCENT = RGBColor(31, 77, 120)
ACCENT2 = RGBColor(46, 116, 181)
MUTED = RGBColor(89, 89, 89)
RED = RGBColor(192, 0, 0)
FILL = "E8EEF5"
FILL_LIGHT = "F4F6F9"
FILL_RED = "FCE4D6"
BORDER = "D9E2F3"


def red_block(text: str) -> str:
    return "\n<RED_START>\n" + text.strip() + "\n<RED_END>\n"


EXPMA_MODULE = r"""
## 第零步：市场状态与择时框架（EXPMA）

> 本节为本版新增的全局市场状态层。它不属于个股风险筛查，也不属于某一个具体选股分支，而是在进入个股筛选之前，先判断当前市场环境、场外情绪与适用打法。

### 0.1 定位：EXPMA不是选股器，而是市场状态与阶段识别器

EXPMA在WJ策略中用于判断市场状态、场外情绪转折与行情阶段，不作为单一个股的核心买卖依据。

正式参数采用：

```text
EXPMA(12,50)
```

其中：

```text
EXPMA12 = 短期价格共识
EXPMA50 = 中期价格共识
```

金叉含义：

```text
EXPMA12 > EXPMA50
= 短期价格共识强于中期价格共识
= 市场短周期风险偏好修复
```

死叉含义：

```text
EXPMA12 < EXPMA50
= 短期价格共识弱于中期价格共识
= 市场短周期风险偏好下降
```

### 0.2 与主线识别、个股筛选的关系

主线识别是客观筛选环节，仍按原策略中的“四驱动判断题材级别”和“真实题材三支点”执行：

```text
驱动同源
产业链可串联
盘面同步
```

EXPMA不负责判断“什么是主线”，也不负责决定“谁是龙头/补涨”。主线识别、龙头筛选、补涨筛选仍按照原有条件逐条取数、逐条验证。

EXPMA对具体筛选流程的改变只体现在执行层：

```text
1. 增加市场状态判断：当前是主升、反弹、震荡，还是退潮。
2. 增加短线出手节奏判断：大盘15分钟金叉后，短线机会更值得观察；大盘15分钟死叉时，减少盲目追高。
3. 增加风险偏好提示：死叉阶段追涨胜率下降，强势股也可能补跌。
4. 不改变候选池生成逻辑：不能因为EXPMA状态不好，就跳过主线识别或不拉候选。
5. 不构成一票否决：EXPMA是择时辅助，不是个股买入资格的硬否决。
```

因此，WJ策略运行时仍应先完整跑出候选，再结合EXPMA判断执行节奏与风险提示。不得用EXPMA替代主线识别，也不得用EXPMA提前锁死“无标的”结论。

### 0.3 多周期使用框架

EXPMA使用时必须遵守：

```text
小趋势服从大趋势。
指数决定环境，板块决定方向，个股决定弹性，EXPMA决定时机。
```

不同周期的作用不同：

| 周期 | 用途 | 说明 |
|---|---|---|
| 15分钟K线EXPMA | 短线进出场节奏 | 主要用于观察大盘场外情绪短周期转折 |
| 60分钟K线EXPMA | 中短线压力与趋势确认 | 用于判断小级别反弹是否受制于更大级别 |
| 日线EXPMA | 波段状态与市场大环境 | 判断市场是否处于更大级别可操作状态 |
| 周线、月线EXPMA | 行业或大级别趋势阶段 | 判断行业是否脱离低谷、进入右侧或主升阶段 |

多周期之间不是平级关系，必须遵守“小级别服从大级别”。60分钟K线由更长时间的交易结果构成，同样观察EXPMA(12,50)时，60分钟级别覆盖的市场记忆显著长于15分钟级别，因此可视为15分钟之上的更大一级别趋势约束。若15分钟级别出现金叉，但60分钟级别仍处于死叉压制，说明小级别情绪尝试修复，但更大一级别趋势仍偏弱，反弹空间可能受限，不能把15分钟金叉机械理解为强反转。

15分钟EXPMA指：

```text
基于15分钟K线收盘价计算出的EXPMA12与EXPMA50。
```

它不是普通分时线，也不是1分钟盘口波动。A股每个交易日约有16根15分钟K线：

```text
4小时交易时间 × 60分钟 / 15分钟 = 16根
```

因此：

```text
15分钟EXPMA12 ≈ 最近12根15分钟K线的指数移动平均 ≈ 最近3小时交易状态
15分钟EXPMA50 ≈ 最近50根15分钟K线的指数移动平均 ≈ 最近3.1个交易日交易状态
```

### 0.4 大盘15分钟EXPMA：短线择时用法

大盘15分钟EXPMA主要用于判断场外情绪的短周期转折和短线进出场节奏。

当大盘15分钟K线EXPMA12上穿EXPMA50时，说明短周期风险偏好开始修复，场外资金可能重新进场。此时可开始重点关注：

```text
前期强势股的超跌反弹
新热点是否出现
新热点中是否有持续逻辑
主线核心标的是否重新走强
```

该信号主要用于短线进出场节奏，不等同于中长期牛市确认。

若15分钟金叉发生在60分钟死叉压制之下，应按弱势反弹处理：此时可能出现情绪冰点或反弹失败，不能因为跌多了就急着抄底；应先观察指数是否还有新低，再等待新的15分钟金叉，同时看有没有新热点和赚钱效应出现。

当大盘15分钟K线EXPMA12下穿EXPMA50时，说明短周期风险偏好下降，场外资金趋于谨慎。此时应注意两类风险：

```text
追涨胜率下降
强势股也容易补跌
```

二者区别如下：

```text
追涨胜率下降 = 不适合新追高，冲高后承接容易不足
强势股容易补跌 = 原本强势或已经持有的高位股，也可能因风险偏好下降而回撤
```

因此，15分钟死叉阶段应减少盲目追高，等待下一次明确转折。

### 0.5 牛市、熊市、震荡市中的用法

牛市中，应以日线级别趋势为主，重点盯龙头、做主升段。15分钟EXPMA可用于优化入场与加减仓节奏，但不应因为小级别波动轻易否定日线主升趋势。

熊市中，15分钟EXPMA金叉主要用于博弈前期强势股的超跌反弹。在大盘15分钟未金叉前，不宜盲目博第二波。

震荡市中，EXPMA容易反复金叉死叉，指标会钝化。此时更考验选股能力，应聚焦前期强势龙头、有资金记忆的妖股、业绩浪标的、具备持续逻辑的新热点核心。震荡市不能机械理解为“金叉就买、死叉就卖”，必须结合个股股性、题材持续性和市场主线强弱。

### 0.6 行业指数的EXPMA用途

会议中认为，EXPMA不适合用来跟踪细分行业指数的短周期波动。细分行业指数在15分钟级别容易受成分股权重、短线资金扰动和局部交易影响，指导意义有限。

行业指数更适合观察日线、周线、月线级别EXPMA，用于判断行业行情推进到什么阶段。

可重点观察：

```text
日线EXPMA金叉：行业进入短期可交易阶段
周线EXPMA金叉：行业中期趋势可能开始形成
月线EXPMA金叉：行业可能逐步脱离长期低谷
```

行业指数中长期EXPMA向上，是行业景气度预期被市场持续确认的重要信号。

这类信号可用于捕捉：

```text
景气度正在提升的行业
长期低位后开始右侧抬头的行业
从谷底逐步脱离的行业
资金开始持续重新定价的行业
```

### 0.7 案例：2018年2月贵州燃气

2018年2月，大盘整体走弱后，资金回流至前期强势股。贵州燃气作为前期强势龙头，在大盘15分钟级别出现转折信号后，出现超跌反弹机会。

案例意义：

```text
弱市中不是完全没有机会；
弱市机会更多集中在前期强势股、老龙头、资金记忆强的标的；
入场应等待大盘15分钟级别出现明确转折；
大盘反弹不代表所有股票都有机会，高位股也可能补跌；
案例不能泛化为“所有前期强势股都会反弹”。
```

### 0.8 信号有效性原则：看状态，不机械看单次交叉

15分钟EXPMA不能机械理解为“一金叉就买、一死叉就卖”。它观察的是大盘短线情绪是否形成比较明确的转强或转弱状态。

```text
若金叉后很快死叉：视为转强失败或噪音信号，不能机械追入。
若一天内反复金叉死叉：说明市场偏震荡钝化，应降低对单次交叉的依赖。
观察15分钟EXPMA时：不只看最新一次交叉，而要看是否形成持续的短线转强/转弱状态。
若15分钟金叉受制于60分钟死叉压制：按小级别反弹处理，反弹空间可能受限，并可能出现情绪冰点或反弹失败。
若出现冰点：不要因为跌多了就急着抄底；先观察是否还有新低，再等新的15分钟金叉，同时看有没有新热点和赚钱效应出现。
```

当前不设置固定“K线根数”或“持续天数”阈值；若后续做量化验证，再由开发者确认是否加入具体参数。
"""


GOVERNANCE_INSERT = r"""
7. **新增内容入版必须逐条确认。** 必须经过开发者确认后才能写入正式规则。不得把讨论中的假设自动升级为正式规则；不得擅自补充会议中没有出现的具体阈值、比例、时间窗口；不得把单一案例泛化成硬规则；不得把辅助判断写成一票否决。
"""


OVERVIEW_INSERT = r"""
**运行顺序补充：** 每次运行WJ策略时，先读“执行定位”和“策略概述”，确认当前是在跑情绪龙头、基本面龙头还是补涨；再看“第零步：市场状态与择时框架（EXPMA）”，判断市场环境、短线节奏和适用打法；随后进入风险筛查、主线识别和具体个股分支。EXPMA决定的是出手环境和节奏，不替代个股筛选条件。
"""


POSITIONING_REPLACEMENT = r"""
> 一句话定位：**用户写完整策略的本意是"写进去的就会被完整运行"。守住这份信任，是最高优先级的纪律。**
"""


INTRADAY_INSERT = r"""
### B.6 大盘15分钟EXPMA执行提示（短线择时辅助）

情绪龙头与补涨策略执行时，应额外观察大盘15分钟K线EXPMA12/50状态：

```text
大盘15分钟金叉：短周期风险偏好修复，可重点观察前期强势股超跌反弹、新热点核心、主线标的重新走强。
大盘15分钟死叉：短周期风险偏好下降，追涨胜率下降，强势股也可能补跌，应减少盲目追高。
```

该提示只用于短线进出场节奏和仓位谨慎度，不构成个股买入的一票否决。
"""


DATA_INSERT = r"""
### 15分钟K线与EXPMA数据源

15分钟EXPMA需要15分钟K线数据。近一年15分钟K线优先使用iFinD或TuShare取得；若接口权限、调用限制或数据覆盖导致无法取得，再考虑其他可验证数据来源。

数据源优先级：

```text
1. iFinD：优先用于近一年15分钟K线数据
2. TuShare分钟线：近一年15分钟K线的备用来源
3. 其他可验证数据来源：仅在前两者不可用时补充
```

若关键数据确实无法取得，且该数据会影响策略判断，应暂停任务并报告，不得凭记忆或印象补写金叉/死叉。
"""


def build_integrated_marked_md() -> str:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    inserted_governance = False
    inserted_expma = False
    inserted_overview = False
    inserted_intraday = False
    inserted_data = False

    for i, line in enumerate(lines):
        if line.startswith("> 一句话定位：**用户写完整策略的本意是"):
            out.append(red_block(POSITIONING_REPLACEMENT))
            continue

        if (not inserted_governance) and line.startswith("**收尾自检"):
            out.append(red_block(GOVERNANCE_INSERT))
            inserted_governance = True

        out.append(line)

        if (not inserted_expma) and line.startswith("> **关键：基本面龙头切合的是"):
            if not inserted_overview:
                out.append(red_block(OVERVIEW_INSERT))
                inserted_overview = True
            out.append(red_block(EXPMA_MODULE))
            inserted_expma = True

        if (not inserted_intraday) and line == "## 止损止盈规则":
            out.insert(len(out) - 1, red_block(INTRADAY_INSERT))
            inserted_intraday = True

        if (not inserted_data) and line == "## 数据获取：优先调用 iFinD 数据源":
            out.append(red_block(DATA_INSERT))
            inserted_data = True

    return "\n".join(out) + "\n"


def markdown_for_review(marked: str) -> str:
    # Keep a readable HTML-color Markdown copy.
    return (
        marked.replace("<RED_START>", '<div style="color:#C00000">\n\n')
        .replace("<RED_END>", "\n\n</div>")
    )


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
        sub = re.split(r"(`[^`]+`)", part)
        for seg in sub:
            if not seg:
                continue
            is_code = seg.startswith("`") and seg.endswith("`")
            run = paragraph.add_run(seg[1:-1] if is_code else seg)
            set_run_font(run, size=base_size, bold=bold, color=color)
            if is_code:
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


def add_table(doc, rows, red=False):
    if not rows:
        return
    cols = max(len(r) for r in rows)
    rows = [r + [""] * (cols - len(r)) for r in rows]
    table = doc.add_table(rows=len(rows), cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_width(table)
    set_table_borders(table, "E2B7AC" if red else BORDER)
    for ri, row in enumerate(table.rows):
        for ci, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            if ri == 0:
                set_cell_shading(cell, FILL_RED if red else FILL)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.15
                add_markdown_runs(p, rows[ri][ci], base_size=9.2, color=RED if red else (ACCENT if ri == 0 else None))
                if ri == 0:
                    for run in p.runs:
                        run.bold = True
                if len(rows[ri][ci]) < 12:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()


def add_callout(doc, text, red=False):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_width(table)
    set_table_borders(table, "E2B7AC" if red else "D0D7E2")
    cell = table.cell(0, 0)
    set_cell_shading(cell, FILL_RED if red else FILL_LIGHT)
    set_cell_margins(cell, top=120, bottom=120, start=160, end=160)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.18
    add_markdown_runs(p, text, base_size=10, color=RED if red else None)
    doc.add_paragraph()


def add_code_block(doc, lines, red=False):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_width(table)
    set_table_borders(table, "E2B7AC" if red else "DADCE0")
    cell = table.cell(0, 0)
    set_cell_shading(cell, "FCE4D6" if red else "F7F7F7")
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
        if red:
            run.font.color.rgb = RED
    doc.add_paragraph()


def build_docx(
    marked: str,
    out_path=OUT_DOCX,
    title_text="WJ策略 v1.4 —— EXPMA整合完整版（红色标注）",
    subtitle_text="红色文字为本次新增或调整内容；未标红部分保留原整合版正文。",
    footer_text="WJ策略 v1.4 EXPMA 整合完整版 · 红色标注",
):
    lines = marked.splitlines()
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    styles = doc.styles
    set_style_font(styles["Normal"], 10.5, after=6, line=1.25)
    set_style_font(styles["Heading 1"], 16, color=ACCENT2, bold=True, before=18, after=10)
    set_style_font(styles["Heading 2"], 13, color=ACCENT2, bold=True, before=14, after=7)
    set_style_font(styles["Heading 3"], 12, color=ACCENT, bold=True, before=10, after=5)
    set_style_font(styles["List Bullet"], 10.5, after=4, line=1.25)
    set_style_font(styles["List Number"], 10.5, after=4, line=1.25)

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    run = title.add_run(title_text)
    set_run_font(run, size=21, bold=True, color=ACCENT)

    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(10)
    add_markdown_runs(sub, subtitle_text, 10, MUTED)

    red = False
    in_code = False
    code_lines = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if line.strip() == "<RED_START>":
            red = True
            i += 1
            continue
        if line.strip() == "<RED_END>":
            red = False
            i += 1
            continue
        if line.strip().startswith("```"):
            if in_code:
                add_code_block(doc, code_lines, red=red)
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
            add_table(doc, rows, red=red)
            continue

        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            heading = clean_inline(m.group(2))
            if level == 1 and heading.startswith("WJ策略 ——"):
                i += 1
                continue
            style = f"Heading {min(level, 3)}"
            p = doc.add_paragraph(style=style)
            add_markdown_runs(
                p,
                heading,
                base_size={2: 13, 3: 12}.get(level, 16),
                color=RED if red else (ACCENT2 if level <= 2 else ACCENT),
            )
            i += 1
            continue

        if line.startswith(">"):
            block = [line.lstrip("> ").strip()]
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i].lstrip("> ").strip())
                i += 1
            add_callout(doc, " ".join([b for b in block if b and b != "---"]), red=red)
            continue

        if re.match(r"^\s*[-*]\s+", line):
            p = doc.add_paragraph(style="List Bullet")
            add_markdown_runs(p, re.sub(r"^\s*[-*]\s+", "", line), base_size=10.2, color=RED if red else None)
            i += 1
            continue

        if re.match(r"^\s*\d+[.、]\s+", line):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.18)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.25
            add_markdown_runs(p, clean_inline(line), base_size=10.2, color=RED if red else None)
            i += 1
            continue

        p = doc.add_paragraph()
        add_markdown_runs(p, clean_inline(line), base_size=10.5, color=RED if red else None)
        i += 1

    if code_lines:
        add_code_block(doc, code_lines, red=red)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_markdown_runs(footer, footer_text, 8.5, MUTED)

    doc.save(out_path)


def main():
    marked = build_integrated_marked_md()
    OUT_MD.write_text(markdown_for_review(marked), encoding="utf-8")
    build_docx(marked)
    print(OUT_MD)
    print(OUT_DOCX)


if __name__ == "__main__":
    main()
