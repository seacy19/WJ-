# -*- coding: utf-8 -*-
"""生成《2025年妖股名单_截至20251106_复算.xlsx》：事件汇总 / 逐日明细 / 口径说明
复算版：原始 2025 名单文件已不在本机，2026-11-07 用与 2026 年名单完全相同的管线复算重建。
"""
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

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

REASON_TODO = '待补——原始2025名单文件已不在本机，本表为2026-11-07用同一管线复算重建；如需逐股原因可另行调研'

NOTES = {
 # 跨年事件：连板自2024年12月起算
 ('sh600693', '2025-01-02'): '跨年事件：连板自2024-12-25起算，2024年名单可能已收录',
 ('sz000533', '2025-01-02'): '跨年事件：连板自2024-12-26起算，2024年名单可能已收录',
 ('sz000759', '2025-01-02'): '跨年事件：连板自2024-12-25起算，2024年名单可能已收录',
 ('sz002184', '2025-01-02'): '跨年事件：连板自2024-12-31起算，2024年名单可能已收录',
 # 事后戴帽：事件期间未ST（baostock逐日isST核验通过），当前名称含ST
 ('sh600423', '2025-01-17'): '事件期间未戴帽，事后被实施风险警示（现名*ST柳化）',
 ('sh600530', '2025-05-15'): '事件期间未戴帽，事后被实施风险警示（现名ST交昂）',
 ('sh603378', '2025-10-30'): '事件期间未戴帽，事后被实施风险警示（现名*ST亚士）',
 ('sz002207', '2025-06-18'): '事件期间未戴帽，事后被实施风险警示（现名*ST准油）',
 ('sz002691', '2025-01-14'): '事件期间未戴帽，事后被实施风险警示（现名*ST冀凯）',
 ('sz002759', '2025-09-10'): '事件期间未戴帽，事后被实施风险警示（现名ST天际）',
 ('sz002977', '2025-05-13'): '事件期间未戴帽，事后被实施风险警示（现名*ST天箭）',
}
# 北交所标的标注
for s, st in [('bj920274', '2025-09-04'), ('bj920351', '2025-04-10')]:
    NOTES.setdefault((s, st), '')
BJ_SET = set(ev[ev.board == 'BJ'].sym)

rows = []
for _, r in ev.iterrows():
    note = NOTES.get((r.sym, r.start), '')
    if r.board == 'BJ' and '北交所' not in note:
        note = (note + '；' if note else '') + '北交所标的（30cm阈值×1/3标准化）'
    rows.append({
        '代码': CODE(r.sym), '名称': r['name'], '板块': BOARD_NAME[r.board],
        '事件开始': r.start, '事件结束': r['end'],
        '达标天数': int(r.n_hit),
        '事件类型': ev_type(r),
        '最大连板': int(r.max_streak) if r.max_streak > 0 else '',
        '连板区间': (f"{r.streak_start}~{r.streak_end}" if isinstance(r.streak_start, str) else ''),
        '最大5日涨幅%（原始）': round(r.max_gain_raw * 100, 1),
        '最大5日涨幅%（标准化）': round(r.max_gain_std * 100, 1),
        '上涨原因': REASON_TODO,
        '归类': '待调研',
        '备注': note,
    })
df_ev = pd.DataFrame(rows)

# ---------- 逐日明细 ----------
d = hits.copy()
d['ev_key'] = list(zip(d.sym, d.event_start))
ev_end = {(r.sym, r.start): r['end'] for _, r in ev.iterrows()}
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
n_double = int((df_ev['事件类型'] == '双达标（连板≥6 + 5日涨幅≥50%）').sum())
bc = df_ev['板块'].value_counts().to_dict()
lines = [
 ('复算说明', '原始2025年名单文件（2025年11月交付）已不在本机。本表为2026-11-07用与《2026年妖股名单》完全相同的管线与口径复算重建，事件/涨幅/连板数据完整；"上涨原因""归类"两列未能复原，标注"待补/待调研"，如需逐股原因可另行调研'),
 ('统计区间', '2025年1月1日至2025年11月6日（与2026年名单截止日对齐），沪深京A股全市场（名单5578只为2026年11月快照，其中165只为2026年新上市、2025年无交易数据，实际覆盖5413只）'),
 ('筛选口径', '满足以下任一条件即记为一个"妖股事件"：①任意连续5个交易日累计涨幅≥50%（标准化口径）；②连续涨停≥6天'),
 ('标准化系数', '主板×1.0；创业板×0.5；科创板×0.5；北交所×1/3（用各板涨跌幅限制对涨幅归一化，消除20cm/30cm与10cm板的天然差异）'),
 ('涨停判定阈值', '主板±9.8%；创业板/科创板±19.8%；北交所±29.8%（按收盘价较前收盘涨跌幅计）'),
 ('连板规则', '连续涨停期间停牌不中断连板计数（与财联社等媒体口径一致）'),
 ('剔除规则', '①事件期间已ST/*ST的股票（依据baostock官方逐日isST字段+名称核验，211只有行情事件股逐一核验通过，0只剔除）；②新股上市初期连续一字板（上市不足20个交易日，本次触发0只）'),
 ('特殊保留案例', '*ST柳化(600423)、ST交昂(600530)、*ST亚士(603378)、*ST准油(002207)、*ST冀凯(002691)、ST天际(002759)、*ST天箭(002977)：事件期间均未戴帽、按正常涨跌幅交易，事后才被实施风险警示，保留并在备注标注"事后戴帽"'),
 ('跨年事件', '2024年12月起板延伸至2025年1月的事件（东百集团、顺钠股份、中百集团、海得控制）已标注，2024年名单中可能已收录'),
 ('已知覆盖缺口', '①名单为2026-11-07快照，2025年内上市且2026年11月前已退市的股票不在名单内（估计影响极小，因退市股多为ST/长期下跌，难触发妖股口径）；②2026年新上市的165只无2025年数据，不影响本区间统计'),
 ('数据源', '行情：baostock后复权日线（329只，含官方isST）+雪球前复权日线（4804只，含官方涨跌幅）+新浪财经北交所日线（280只，不复权）；股票名单：新浪财经hs_a全名单快照（5578只）；ST核验：baostock逐日isST字段'),
 ('数据验证', '①头部结果与公开认知一致：天普股份15连板（2025年8-9月）、新炬网络/上纬新材/美邦股份10连板、成飞集成/合富中国/西藏旅游/杭钢股份/信隆健康9连板；②全部244个事件逐一通过ST窗口核验，无事件期内戴帽标的'),
 ('事件合并规则', '同一只股票相邻达标日间隔≤5个交易日合并为同一事件；同一股票可对应多个事件'),
 ('统计结果', f'共{len(df_ev)}个妖股事件，涉及{n_stock}只股票；其中主板{bc.get("主板",0)}、创业板{bc.get("创业板",0)}、科创板{bc.get("科创板",0)}、北交所{bc.get("北交所",0)}；双达标{n_double}个、纯涨幅达标{len(df_ev)-n_double-(df_ev["事件类型"]=="连板达标（≥6连板）").sum():.0f}个'),
 ('免责声明', '本表为量化口径下的客观筛选，不构成投资建议'),
]
df_spec = pd.DataFrame(lines, columns=['项目', '说明'])

# ---------- 写出 ----------
out = '/Users/seacy/Documents/Kimi/Workspaces/wj strategy/scan2025/2025年妖股名单_截至20251106_复算.xlsx'
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
