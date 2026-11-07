import json, os, sys, time, random, urllib.request, gzip, csv, threading
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.join(BASE, 'data', 'kline')
UA_LIST = [
 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]
HOSTS = ['https://ifzq.gtimg.cn', 'https://web.ifzq.gtimg.cn', 'https://proxy.finance.qq.com/ifzqgtimg']
cooldown_until = {'t': 0.0}
lock = threading.Lock()

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': random.choice(UA_LIST)})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(data)
        return data.decode('utf-8','ignore')

def hit_cooldown():
    with lock:
        cooldown_until['t'] = time.time() + 12

def wait_cooldown():
    while True:
        with lock:
            rem = cooldown_until['t'] - time.time()
        if rem <= 0:
            return
        time.sleep(min(rem, 3))

def fetch_tx(sym):
    last = None
    for host in HOSTS:
        wait_cooldown()
        try:
            url = '%s/appstock/app/fqkline/get?param=%s,day,2025-09-01,2026-11-07,640,qfq' % (host, sym)
            j = json.loads(get(url))
            d = j['data'].get(sym) or {}
            rows = d.get('qfqday') or d.get('day') or []
            if rows:
                return [(r[0], r[1], r[3], r[4], r[2], r[5] if len(r) > 5 else '') for r in rows]
            last = 'empty'
        except urllib.error.HTTPError as e:
            last = 'HTTP %s' % e.code
            if e.code in (501, 502, 503, 429):
                hit_cooldown()
        except Exception as e:
            last = repr(e)[:80]
    raise RuntimeError(last)

def fetch_bj(sym):
    wait_cooldown()
    url = ('https://quotes.sina.cn/cn/api/jsonp_v2.php/var=/CN_MarketDataService.getKLineData'
           '?symbol=%s&scale=240&ma=no&datalen=640' % sym)
    t = get(url)
    body = t[t.index('(')+1:t.rindex(')')]
    rows = json.loads(body)
    return [(r['day'], r['open'], r['high'], r['low'], r['close'], r.get('volume','')) for r in rows]

def fetch_one(sym):
    path = os.path.join(KDIR, sym + '.csv')
    if os.path.exists(path):
        return sym, True, 'skip'
    try:
        rows = fetch_bj(sym) if True else None
        rows = [r for r in rows if r[0] >= '2024-11-15' and r[0] <= '2025-11-07']
        if not rows:
            return sym, False, 'empty'
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['date','open','high','low','close','volume'])
            w.writerows(rows)
        return sym, True, str(len(rows))
    except Exception as e:
        return sym, False, repr(e)[:80]

def main():
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 260.0
    universe = json.load(open(os.path.join(BASE, 'data', 'universe.json')))
    syms = sorted(s for s in universe if s.startswith('bj'))
    done = set(f[:-4] for f in os.listdir(KDIR) if f.endswith('.csv'))
    todo = [s for s in syms if s not in done]
    print('todo=%d done=%d' % (len(todo), len(done)), flush=True)
    if not todo:
        return
    t0 = time.time()
    ok = fail = 0
    fails = {}
    from concurrent.futures import as_completed
    idx = 0
    CHUNK = 500
    while idx < len(todo) and time.time() - t0 < budget:
        batch = todo[idx:idx+CHUNK]
        idx += CHUNK
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fetch_one, s): s for s in batch}
            for fut in as_completed(futs):
                sym, success, msg = fut.result()
                if success: ok += 1
                else: fail += 1; fails[sym] = msg
        print('progress ok=%d fail=%d elapsed=%.0fs' % (ok, fail, time.time()-t0), flush=True)
    print('BATCH ok=%d fail=%d remaining~%d' % (ok, fail, len(todo)-ok-fail), flush=True)
    if fails:
        with open(os.path.join(BASE,'data','fail_bj25.json'),'w') as f:
            json.dump(fails, f, ensure_ascii=False, indent=1)
        items = list(fails.items())
        print('sample fails:', items[:4])

if __name__ == '__main__':
    main()
