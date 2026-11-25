import json,time,urllib.request,urllib.parse,sys
B='https://api.contexto.me/machado/en'
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def get(path):
    time.sleep(0.6)
    req=urllib.request.Request(B+path,headers=UA)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,dict(r.headers),json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: body=json.loads(e.read().decode())
        except Exception: body=None
        return e.code,dict(e.headers),body
out={}
st,h,b=get('/top/1500')
print('TOP status',st,type(b).__name__, list(b.keys()) if isinstance(b,dict) else len(b))
print({k:h.get(k) for k in ['Server','server','Cache-Control','cache-control','X-Powered-By','Via','CF-Ray','Age','ETag','Last-Modified']})
out['top_1500']=b
w=b.get('words') if isinstance(b,dict) else b
print('n top',len(w) if w else None); print(str(w)[:600]); print(str(w)[-300:])
# tip
for d in [0,1,2,299,500,1000,5000,10000,20000,30000,40000,50000,70000,100000,200000,317755,400000]:
    st,h,b=get(f'/tip/1500/{d}'); print('tip',d,st,b); out[f'tip_{d}']=b
json.dump(out,open(sys.argv[1],'w'),ensure_ascii=False,indent=0)
