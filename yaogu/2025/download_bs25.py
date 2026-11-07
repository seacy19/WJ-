import json, os, sys, time, csv
import baostock as bs

BASE = os.path.dirname(os.path.abspath(__file__))
K2 = os.path.join(BASE, 'data', 'kline2')
os.makedirs(K2, exist_ok=True)

def main():
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 250.0
    universe = json.load(open(os.path.join(BASE, 'data', 'universe.json')))
    syms = sorted(s for s in universe if not s.startswith('bj'))
    done = set(f[:-4] for f in os.listdir(K2) if f.endswith('.csv'))
    todo = [s for s in syms if s not in done]
    print('todo=%d done=%d' % (len(todo), len(done)), flush=True)
    if not todo:
        return
    lg = bs.login()
    assert lg.error_code == '0', lg.error_msg
    t0 = time.time()
    ok = fail = 0
    fails = {}
    for s in todo:
        if time.time() - t0 > budget:
            break
        code = s[:2] + '.' + s[2:]
        try:
            rs = bs.query_history_k_data_plus(code,
                "date,open,high,low,close,volume,pctChg,isST",
                start_date='2024-11-15', end_date='2025-11-07',
                frequency="d", adjustflag="1")
            rows = rs.get_data()
            if len(rows) == 0:
                fail += 1; fails[s] = 'empty'
                continue
            with open(os.path.join(K2, s + '.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['date','open','high','low','close','volume','pctChg','isST'])
                for _, r in rows.iterrows():
                    w.writerow(list(r))
            ok += 1
        except Exception as e:
            fail += 1; fails[s] = repr(e)[:80]
        if (ok + fail) % 500 == 0:
            print('progress ok=%d fail=%d elapsed=%.0fs' % (ok, fail, time.time()-t0), flush=True)
    bs.logout()
    print('BATCH ok=%d fail=%d remaining=%d' % (ok, fail, len(todo)-ok-fail), flush=True)
    if fails:
        json.dump(fails, open(os.path.join(BASE,'data','fail_bs25.json'),'w'), ensure_ascii=False, indent=1)
        print('sample fails:', list(fails.items())[:5])

if __name__ == '__main__':
    main()
