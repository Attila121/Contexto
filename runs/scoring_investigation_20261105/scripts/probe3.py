import json,time,urllib.request,sys
B='https://api.contexto.me/machado/en'
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def get(path):
    time.sleep(0.7)
    req=urllib.request.Request(B+path,headers=UA)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,None
games=[0,1,103,250,500,750,1000,1011,1250,1400,1490]+list(range(1498,1508))
out={}
for g in games:
    st,b=get(f'/top/{g}')
    w=(b or {}).get('words') if isinstance(b,dict) else None
    out[str(g)]=w
    print(g,st,len(w) if w else b, (w or [])[:6],flush=True)
json.dump(out,open(sys.argv[1],'w'),ensure_ascii=False,indent=0)
