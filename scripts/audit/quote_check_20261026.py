import sys, json
from pathlib import Path
sys.path.insert(0, '.tushare_runtime')
import requests
import tushare as ts
from concurrent.futures import ThreadPoolExecutor
codes=['sz300660','sh600580','sh603728','sz003021','sz002097','sz301502','sh600312','sh600900','sh688213','sh603933','sh603350']
secret=json.loads(Path(r'C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json').read_text(encoding='utf8'))
pro=ts.pro_api(secret.get('TUSHARE_TOKEN') or secret.get('TUSHARE_PRO_TOKEN'))
meta=pro.stock_basic(exchange='',list_status='L',fields='ts_code,name,industry')
codes=[('sh' if c.endswith('.SH') else 'sz' if c.endswith('.SZ') else 'bj')+c[:6] for c in meta.ts_code]
industry={r.ts_code[:6]:r.industry for r in meta.itertuples()}
def fetch(batch):
    r=requests.get('https://qt.gtimg.cn/q='+','.join(batch),timeout=20)
    r.encoding='gbk'
    return r.text
batches=[codes[i:i+100] for i in range(0,len(codes),100)]
with ThreadPoolExecutor(max_workers=6) as pool:
    texts=list(pool.map(fetch,batches))
out=[]
for line in '\n'.join(texts).splitlines():
    if '~' not in line: continue
    a=line.split('"')[1].split('~')
    if len(a)<46 or not a[3] or not a[30].startswith('20261023'): continue
    out.append({'name':a[1],'code':a[2],'industry':industry.get(a[2]),'last':float(a[3]),'previous':float(a[4]),'open':float(a[5]),'time':a[30],'change_pct':float(a[32]),'high':float(a[33]),'low':float(a[34]),'volume':float(a[6]),'amount_yi':float(a[37])/10000,'turn':float(a[38]) if a[38] else None,'pe':float(a[39]) if a[39] else None,'mv_yi':float(a[45]) if a[45] else None})
Path('quote_check_20261026_output.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'count':len(out),'up':sum(x['change_pct']>0 for x in out),'down':sum(x['change_pct']<0 for x in out),'amount_yi':sum(x['amount_yi'] for x in out),'top':sorted([x for x in out if 'ST' not in x['name']],key=lambda x:x['change_pct'],reverse=True)[:50]},ensure_ascii=False))
