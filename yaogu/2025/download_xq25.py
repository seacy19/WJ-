import json, os, sys, time, csv, random, threading, urllib.request, http.cookiejar
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.abspath(__file__))
K3 = os.path.join(BASE, 'data', 'kline3')
os.makedirs(K3, exist_ok=True)
UA = {'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'}

tl = threading.local()

def get_opener():
    if not getattr(tl, 'opener', None):
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.open(urllib.request.Request('https://xueqiu.com/', headers=UA), timeout=15).read()
        tl.opener = op
        tl.tried = 0
    return tl.opener

def fetch(sym):
    # sym like sh600519 -> SH600519
    xq = sym.upper()
    url = ('https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol=%s&begin=%d&period=day'
           '&type=before&count=-520&indicator=kline' % (xq, int(time.time()*1000)))
    for attempt in range(3):
        op = get_opener()
        try:
            req = urllib.request.Request(url, headers={**UA, 'Referer':'https://xueqiu.com/S/'+xq})
            j = json.loads(op.open(req, timeout=15).read().decode())
            items = j['data']['item']
            rows = []
            for it in items:
                d = time.strftime('%Y-%m-%d', time.localtime(it[0]/1000))
                rows.append((d, it[2], it[3], it[4], it[5], it[1], it[7]))  # date,o,h,l,c,vol,percent
            return rows
        except Exception as e:
            tl.opener = None  # refresh cookie next time
            last = repr(e)[:80]
            time.sleep(1 + random.random()*2)
    raise RuntimeError(last)

def fetch_one(sym):
    path = os.path.join(K3, sym + '.csv')
    if os.path.exists(path):
        return sym, True, 'skip'
    try:
        rows = fetch(sym)
        rows = [r for r in rows if r[0] >= '2024-11-15' and r[0] <= '2025-11-07']
        if not rows:
            return sym, False, 'empty'
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['date','open','high','low','close','volume','percent'])
            w.writerows(rows)
        return sym, True, str(len(rows))
    except Exception as e:
        return sym, False, repr(e)[:80]

def main():
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 250.0
    universe = json.load(open(os.path.join(BASE, 'data', 'universe.json')))
    # sh/sz stocks NOT already covered by baostock (kline2)
    k2 = set(f[:-4] for f in os.listdir(os.path.join(BASE,'data','kline2')) if f.endswith('.csv'))
    syms = sorted(s for s in universe if not s.startswith('bj') and s not in k2)
    done = set(f[:-4] for f in os.listdir(K3) if f.endswith('.csv'))
    todo = [s for s in syms if s not in done]
    print('xq todo=%d done=%d' % (len(todo), len(done)), flush=True)
    if not todo:
        return
    t0 = time.time()
    ok = fail = 0
    fails = {}
    idx = 0
    CHUNK = 400
    while idx < len(todo) and time.time() - t0 < budget:
        batch = todo[idx:idx+CHUNK]
        idx += CHUNK
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(fetch_one, s) for s in batch]
            for fut in as_completed(futs):
                sym, success, msg = fut.result()
                if success: ok += 1
                else: fail += 1; fails[sym] = msg
        print('progress ok=%d fail=%d elapsed=%.0fs' % (ok, fail, time.time()-t0), flush=True)
    print('BATCH ok=%d fail=%d remaining=%d' % (ok, fail, len(todo)-ok-fail), flush=True)
    if fails:
        json.dump(fails, open(os.path.join(BASE,'data','fail_xq25.json'),'w'), ensure_ascii=False, indent=1)
        print('sample fails:', list(fails.items())[:5])

if __name__ == '__main__':
    main()
