import json, os, csv, baostock as bs
BASE = os.path.dirname(os.path.abspath(__file__))
need = json.load(open(os.path.join(BASE,'data','need_bs.json')))
lg = bs.login(); assert lg.error_code=='0'
out = {}
for s in need:
    code = s[:2]+'.'+s[2:]
    rs = bs.query_history_k_data_plus(code, "date,pctChg,isST", start_date='2024-11-15', end_date='2025-11-07', frequency="d", adjustflag="1")
    rows = rs.get_data()
    out[s] = {r['date']: int(r['isST']) for _, r in rows.iterrows()}
bs.logout()
json.dump(out, open(os.path.join(BASE,'data','bs_st.json'),'w'))
print('fetched', len(out))
