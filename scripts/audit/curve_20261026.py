import sys,json
from pathlib import Path
sys.path.insert(0,'.tushare_runtime')
import tushare as ts
import pandas as pd
s=json.loads(Path(r'C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json').read_text(encoding='utf8'))
p=ts.pro_api(s.get('TUSHARE_TOKEN') or s.get('TUSHARE_PRO_TOKEN'))
quotes={x['code']:x for x in json.loads(Path('quote_check_20261026_output.json').read_text(encoding='utf8'))}
codes=['300660.SZ','600580.SH','603728.SH','003021.SZ','002097.SZ','301502.SZ','600312.SH','600900.SH','688213.SH','603933.SH','603350.SH','688686.SH','688279.SH','300296.SZ','002249.SZ','300124.SZ','002472.SZ','002050.SZ']
out=[]
codes += ['002979.SZ','002837.SZ','300684.SZ','300990.SZ','301018.SZ','300249.SZ']
for code in codes:
    q=quotes[code[:6]]
    d=ts.pro_bar(api=p,ts_code=code,start_date='20250101',end_date='20261023',adj='qfq').sort_values('trade_date')
    if str(d.iloc[-1].trade_date)!='20261023':
        d=pd.concat([d,pd.DataFrame([{'trade_date':'20261023','close':q['last'],'open':q['open'],'high':q['high'],'low':q['low']}])],ignore_index=True)
    c=d.close.astype(float)
    ma={n:float(c.iloc[-n:].mean()) for n in [5,10,20,60,120,250]}
    slopes={n:100*(ma[n]/float(c.iloc[-n-20:-20].mean())-1) for n in [20,60,120,250]}
    seq=[q['last']]+list(ma.values())
    out.append({**q,'ma':{n:round(v,2) for n,v in ma.items()},'slopes':{n:round(v,2) for n,v in slopes.items()},'full_curve':all(a>=b for a,b in zip(seq,seq[1:])),'all_slopes_up':all(v>0 for v in slopes.values()),'ret5':round(100*(c.iloc[-1]/c.iloc[-6]-1),2),'ret10':round(100*(c.iloc[-1]/c.iloc[-11]-1),2),'ret20':round(100*(c.iloc[-1]/c.iloc[-21]-1),2),'range65_pre':round(100*(c.iloc[-66:-1].max()/c.iloc[-66:-1].min()-1),2),'drawdown250':round(100*(c.iloc[-1]/c.iloc[-250:].max()-1),2)})
Path('curve_20261026_output.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False))
