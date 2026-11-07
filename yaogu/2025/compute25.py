import json, os, csv, math
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(BASE, 'data')
universe = json.load(open(os.path.join(D, 'universe.json')))

def board_of(sym):
    if sym.startswith('bj'): return 'BJ'
    code = sym[2:]
    if sym.startswith('sh'):
        return 'KC' if code.startswith(('688','689')) else 'ZB'
    else:
        return 'CY' if code.startswith(('300','301','302')) else 'ZB'

THR = {'ZB': 9.8, 'CY': 19.8, 'KC': 19.8, 'BJ': 29.8}
FAC = {'ZB': 1.0, 'CY': 0.5, 'KC': 0.5, 'BJ': 1/3.0}

W_START, W_END = '2025-01-01', '2025-11-06'

def load(sym):
    p2 = os.path.join(D, 'kline2', sym + '.csv')
    p3 = os.path.join(D, 'kline3', sym + '.csv')
    p1 = os.path.join(D, 'kline', sym + '.csv')
    if os.path.exists(p2):
        df = pd.read_csv(p2, dtype={'date': str})
        df = df.rename(columns={'pctChg': 'pct'})
        df['pct'] = df['pct'].astype(float)
        df['isST'] = df['isST'].astype(int)
    elif os.path.exists(p3):
        df = pd.read_csv(p3, dtype={'date': str})
        df = df.rename(columns={'percent': 'pct'})
        df['pct'] = df['pct'].astype(float)
        df['isST'] = -1  # unknown
    elif os.path.exists(p1):
        df = pd.read_csv(p1, dtype={'date': str})
        df['pct'] = df['close'].astype(float).pct_change() * 100
        df['isST'] = -1
    else:
        return None
    df = df.sort_values('date').reset_index(drop=True)
    df['close'] = df['close'].astype(float)
    return df

events = []
hits_rows = []
suspects = []  # (sym, reason)
stats = {'stocks': 0, 'nodata': 0}

for sym, name in sorted(universe.items()):
    df = load(sym)
    if df is None or len(df) < 6:
        stats['nodata'] += 1
        continue
    stats['stocks'] += 1
    board = board_of(sym)
    thr, fac = THR[board], FAC[board]
    dates = df['date'].tolist()
    closes = df['close'].tolist()
    pcts = df['pct'].tolist()
    issts = df['isST'].tolist()
    n = len(df)
    # board day flags
    is_board_day = []
    for i in range(n):
        if pcts[i] is None or (isinstance(pcts[i], float) and math.isnan(pcts[i])):
            is_board_day.append(False); continue
        if issts[i] == 1:
            is_board_day.append(False); continue
        is_board_day.append(pcts[i] >= thr)
    # streaks
    streaks = []
    i = 0
    while i < n:
        if is_board_day[i]:
            j = i
            while j + 1 < n and is_board_day[j+1]:
                j += 1
            streaks.append((i, j))
            i = j + 1
        else:
            i += 1
    # hit days
    hit = set()
    gain_at = {}
    for i in range(5, n):
        g = closes[i] / closes[i-5] - 1
        gs = g * fac
        if gs >= 0.50 and W_START <= dates[i] <= W_END:
            # ST check: if stock currently ST (baostock isST==1 on that day) skip
            if issts[i] == 1:
                continue
            hit.add(i)
            gain_at[i] = (g, gs)
    for (a, b) in streaks:
        if b - a + 1 >= 6:
            for i in range(a, b+1):
                if W_START <= dates[i] <= W_END:
                    hit.add(i)
    if not hit:
        continue
    hit_sorted = sorted(hit)
    # aggregate: gap > 5 trading days -> new event
    eps = []
    cur = [hit_sorted[0]]
    for i in hit_sorted[1:]:
        if i - cur[-1] <= 5:
            cur.append(i)
        else:
            eps.append(cur); cur = [i]
    eps.append(cur)
    for ep in eps:
        a, b = ep[0], ep[-1]
        # extend window to include streak bounds for intersecting streaks
        ev_streaks = [(s, t) for (s, t) in streaks if not (t < a or s > b)]
        max_streak = max((t - s + 1 for (s, t) in ev_streaks), default=0)
        st_start = st_end = None
        if ev_streaks:
            longest = max(ev_streaks, key=lambda x: x[1]-x[0])
            st_start, st_end = dates[longest[0]], dates[longest[1]]
        gains = [(i, gain_at[i]) for i in ep if i in gain_at]
        max_g = max((v[0] for _, v in gains), default=None)
        max_gs = max((v[1] for _, v in gains), default=None)
        qual_gain = max_gs is not None and max_gs >= 0.50
        qual_streak = max_streak >= 6
        sessions_at_start = a + 1  # rows up to event start
        new_stock = sessions_at_start < 20
        st_flag = any(issts[i] == 1 for i in range(a, b+1))
        st_unknown = any(issts[i] == -1 for i in range(a, b+1)) and board in ('CY','KC','BJ')
        events.append({
            'sym': sym, 'name': name, 'board': board,
            'start': dates[a], 'end': dates[b], 'n_hit': len(ep),
            'max_gain_raw': max_g, 'max_gain_std': max_gs,
            'max_streak': max_streak, 'streak_start': st_start, 'streak_end': st_end,
            'qual_gain': qual_gain, 'qual_streak': qual_streak,
            'new_stock': new_stock, 'st_flag': st_flag, 'st_unknown': st_unknown,
            'n_sessions': n,
        })
        if st_unknown and ('ST' in name):
            suspects.append((sym, name, dates[a], dates[b]))
        for i in ep:
            g, gs = gain_at.get(i, (None, None))
            # streak len covering day i
            sl = 0
            for (s, t) in streaks:
                if s <= i <= t:
                    sl = t - s + 1
            hits_rows.append({
                'sym': sym, 'name': name, 'board': board, 'date': dates[i],
                'pct': round(pcts[i], 2) if pcts[i] == pcts[i] else None,
                'gain5_raw': None if g is None else round(g*100, 2),
                'gain5_std': None if gs is None else round(gs*100, 2),
                'is_board': is_board_day[i], 'streak_len': sl,
                'event_start': dates[a],
            })

ev = pd.DataFrame(events)
hits = pd.DataFrame(hits_rows)
print('stocks processed:', stats)
print('raw events:', len(ev), 'stocks:', ev.sym.nunique() if len(ev) else 0)
print('new_stock excluded events:', int(ev.new_stock.sum()))
print('st_flag events:', int(ev.st_flag.sum()))
print('qualifying (before exclusions):', int(((ev.qual_gain) | (ev.qual_streak)).sum()))
# apply exclusions
final = ev[(ev.qual_gain | ev.qual_streak) & (~ev.new_stock) & (~ev.st_flag)]
print('FINAL events:', len(final), 'stocks:', final.sym.nunique())
print('by board:', final.board.value_counts().to_dict())
print('dual qual:', int((final.qual_gain & final.qual_streak).sum()))
final.to_csv(os.path.join(D, 'events.csv'), index=False)
ev.to_csv(os.path.join(D, 'events_all.csv'), index=False)
hits.to_csv(os.path.join(D, 'hits.csv'), index=False)
json.dump(suspects, open(os.path.join(D, 'suspects.json'), 'w'), ensure_ascii=False, indent=1)
# monthly dist
final['month'] = final['start'].str[:7]
print(final.groupby('month').size().to_dict())
# top streaks
print('\nTOP streaks:')
top = final.sort_values('max_streak', ascending=False).head(25)
for _, r in top.iterrows():
    print('%s %s %s 板 %s~%s max5d_std=%.1f%% %s' % (r.sym, r['name'], r.max_streak, r.streak_start, r.streak_end, (r.max_gain_std or 0)*100, r.start))
