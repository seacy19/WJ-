# -*- coding: utf-8 -*-
"""生成《2026年妖股名单_截至20261106.xlsx》：逐日明细 / 事件汇总 / 口径说明"""
import pandas as pd, importlib.util
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

def load(f, attr):
    spec = importlib.util.spec_from_file_location('r', f)
    r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
    return getattr(r, attr)

RA = load('data/reasons.py', 'REASONS')
RB = load('data/reasons_b.py', 'B_REASONS')

ev = pd.read_csv('data/events.csv')
hits = pd.read_csv('data/hits.csv')

BOARD_NAME = {'ZB': '主板', 'CY': '创业板', 'KC': '科创板', 'BJ': '北交所'}
CODE = lambda s: s[2:]

# ---------- 事件汇总 ----------
ev = ev.sort_values(['start', 'sym']).reset_index(drop=True)
key2ev = {(r.sym, r.start): i for i, r in ev.iterrows()}

def ev_type(r):
    if r.qual_gain and r.qual_streak: return '双达标（连板≥6 + 5日涨幅≥50%）'
    if r.qual_streak: return '连板达标（≥6连板）'
    return '涨幅达标（5日累计≥50%标准化）'

NOTES = {
 ('sz002931','2026-01-05'): '跨年事件：2025年12月17日起板，2025年名单可能已收录；年内最高连板股',
 ('sz001331','2026-01-06'): '跨年事件：2025年12月12日起板，2025年名单可能已收录',
 ('sh601698','2026-01-05'): '连板自2025年12月31日跨年起算',
 ('sz002413','2026-01-05'): '连板自2025年12月29日跨年起算',
 ('sz002718','2026-01-07'): '连板自2025年12月23日跨年起算',
 ('sh600370','2026-03-18'): '事件期间未戴帽（按10%涨跌幅交易），事后被实施风险警示',
 ('sz002082','2026-03-30'): '事件期间未戴帽（按10%涨跌幅交易），事后被实施风险警示',
 ('bj920725','2026-06-03'): '北交所唯一入选标的',
 ('sz001259','2026-05-11'): '部分媒体口径为9连板',
 ('sh603137','2026-06-12'): '媒体口径8连板（含停牌前后）',
 ('sh600371','2026-08-25'): '媒体口径10天7板',
 ('sh600613','2026-08-18'): '媒体口径11天7板',
 ('sz002827','2026-08-03'): '媒体口径9天6板',
 ('sh603221','2026-07-21'): '媒体口径12天11板',
 ('sz002969','2026-01-05'): '跨年延伸：2025/12/17-2026/1/23区间累计+408%（19天14板），两度停牌核查',
 ('sh600825','2026-09-21'): '年内主板最高连板（10连板），10/13停牌核查',
}

rows = []
for _, r in ev.iterrows():
    cat, reason = ('A', RA[r.sym][1]) if r.sym in RA else ('B', RB[r.sym])
    note = NOTES.get((r.sym, r.start), '')
    rows.append({
        '代码': CODE(r.sym), '名称': r['name'], '板块': BOARD_NAME[r.board],
        '事件开始': r.start, '事件结束': r['end'],
        '达标天数': int(r.n_hit),
        '事件类型': ev_type(r),
        '最大连板': int(r.max_streak) if r.max_streak > 0 else '',
        '连板区间': (f"{r.streak_start}~{r.streak_end}" if isinstance(r.streak_start, str) else ''),
        '最大5日涨幅%（原始）': round(r.max_gain_raw * 100, 1),
        '最大5日涨幅%（标准化）': round(r.max_gain_std * 100, 1),
        '上涨原因': reason,
        '归类': '个股事件驱动' if cat == 'A' else '主题/板块行情',
        '备注': note,
    })
df_ev = pd.DataFrame(rows)

# ---------- 逐日明细 ----------
d = hits.copy()
d['ev_key'] = list(zip(d.sym, d.event_start))
ev_end = {(r.sym, r.start): r['end'] for _, r in ev.iterrows()}
ev_type_map = {(r.sym, r.start): df_ev.loc[key2ev[(r.sym, r.start)], '事件类型'] for _, r in ev.iterrows()}
d = d.sort_values(['event_start', 'sym', 'date'])
df_hit = pd.DataFrame({
    '代码': d.sym.map(CODE), '名称': d['name'], '板块': d.board.map(BOARD_NAME),
    '日期': d.date, '当日涨跌幅%': d.pct.round(2),
    '5日累计涨幅%（原始）': d.gain5_raw.round(1),
    '5日累计涨幅%（标准化）': d.gain5_std.round(1),
    '是否涨停': d.is_board.map({True: '是', False: '否'}),
    '当日连板数': d.streak_len.where(d.streak_len > 0, ''),
    '所属事件': [f"{s}~{ev_end[k]}" for s, k in zip(d.event_start, d.ev_key)],
})

# ---------- 口径说明 ----------
n_stock = df_ev['代码'].nunique()
lines = [
 ('统计区间', '2026年1月1日至2026年11月6日（最新交易日），沪深京A股全市场5578只'),
 ('筛选口径（沿用2025年名单口径）', '满足以下任一条件即记为一个"妖股事件"：①任意连续5个交易日累计涨幅≥50%（标准化口径）；②连续涨停≥6天'),
 ('标准化系数', '主板×1.0；创业板×0.5；科创板×0.5；北交所×1/3（即用各板涨跌幅限制对涨幅做归一化，消除20cm/30cm板与10cm板的天然差异）'),
 ('涨停判定阈值', '主板±9.8%；创业板/科创板±19.8%；北交所±29.8%（按收盘价较前收盘涨跌幅计）'),
 ('连板规则', '连续涨停期间停牌不中断连板计数（与财联社等媒体口径一致，如锋龙股份停牌核查后复牌续板仍计为连续）'),
 ('剔除规则', '①事件期间已ST/*ST的股票（依据baostock官方逐日isST字段+名称核验）；②新股上市初期连续一字板（上市不足20个交易日）。本次扫描两类剔除触发均为0'),
 ('特殊保留案例', '*ST三房(600370)、ST万邦(002082)事件期间尚未戴帽、按10%涨跌幅正常交易，经公告核验后保留，备注标注"事后戴帽"'),
 ('跨年事件', '2025年12月起板延伸至2026年1月的事件（锋龙股份、胜通能源、嘉美包装等）已标注，2025年名单中可能已收录'),
 ('退市股覆盖', '2026年退市股（*ST长药、广道数字、东方通、德邦、信达等）均为ST或吸收合并，口径内自动覆盖，无遗漏影响'),
 ('数据源', '行情：baostock后复权日线（1780只，含官方isST）+雪球前复权日线（3443只，含官方涨跌幅）+新浪财经北交所日线（355只，不复权）；股票名单：新浪财经hs_a全名单（5578只）'),
 ('数据验证', '①2026-01-12全市场涨停数自测187家 vs 媒体报道181家，吻合；②锋龙股份18连板、胜通能源14连板与财联社报道一致；③北交所涨跌幅按不复权价计算，30cm阈值判定'),
 ('事件合并规则', '同一只股票相邻达标日间隔≤5个交易日合并为同一事件；同一股票可对应多个事件'),
 ('上涨原因分档', 'A档=个股事件驱动（连板股逐只调研核实，含公告、澄清、监管动态）；B档=主题/板块行情（冷门股按当月市场主线+行业题材批量归类，月度主线：1月科技开年+黄金白银，2月AI算力+春节消费，3月绿电算电协同+创新药，4月算力硬件+地产链，5月电力+AI硬件，6月小金属+培育钻石+核聚变，7月跨界并购+医药，8月黄金+农业粮食+医药+数字货币，9月出版传媒+绿电+大金融+消费，10月机器人+固态电池+易主，11月初医药+影视+有色）'),
 ('统计结果', f'共{len(df_ev)}个妖股事件，涉及{n_stock}只股票；其中主板166、创业板10、北交所1、科创板0；双达标37个、纯涨幅达标140个'),
 ('免责声明', '本表为量化口径下的客观筛选与公开信息整理，上涨原因基于公开报道与公司公告，不构成投资建议'),
]
df_spec = pd.DataFrame(lines, columns=['项目', '说明'])

# ---------- 写出 ----------
from pathlib import Path
out = str(Path(__file__).resolve().parent / '2026年妖股名单_截至20261106.xlsx')
with pd.ExcelWriter(out, engine='openpyxl') as w:
    df_ev.to_excel(w, sheet_name='事件汇总', index=False)
    df_hit.to_excel(w, sheet_name='逐日明细', index=False)
    df_spec.to_excel(w, sheet_name='口径说明', index=False)
    wb = w.book
    for name, df in [('事件汇总', df_ev), ('逐日明细', df_hit), ('口径说明', df_spec)]:
        ws = wb[name]
        hfill = PatternFill('solid', fgColor='1F4E79')
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF', size=11)
            c.fill = hfill
            c.alignment = Alignment(horizontal='center', vertical='center')
        ws.freeze_panes = 'A2'
        for j, col in enumerate(df.columns, 1):
            if col in ('上涨原因', '说明'):
                width = 90
            elif col in ('所属事件',):
                width = 24
            elif col in ('备注',):
                width = 42
            else:
                width = max(10, min(20, max(len(str(col)), int(df[col].astype(str).str.len().quantile(0.95) if len(df) else 10)) + 3))
            ws.column_dimensions[get_column_letter(j)].width = width
        if name in ('事件汇总', '口径说明'):
            wrap_col = 'M' if name == '事件汇总' else 'B'
            for row in ws.iter_rows(min_row=2, min_col=1, max_col=ws.max_column):
                for c in row:
                    if c.column_letter == wrap_col:
                        c.alignment = Alignment(wrap_text=True, vertical='top')
                    else:
                        c.alignment = Alignment(vertical='top')
print('written:', out)
print('事件汇总', len(df_ev), '行；逐日明细', len(df_hit), '行；口径说明', len(df_spec), '行')
print('股票数', n_stock)
print(df_ev['板块'].value_counts().to_dict())
print(df_ev['事件类型'].value_counts().to_dict())
