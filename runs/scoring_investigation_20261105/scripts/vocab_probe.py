import json,random,re,sys,time,urllib.request,urllib.parse,os
import numpy as np
SP=sys.argv[1]; random.seed(20261104)
words=[str(w) for w in np.load(os.path.join(SP,'vec','x','glove6B300.npz'))['words']]
F=[w for w in words if re.fullmatch(r'[a-z]+',w)]
print('filtered',len(F),flush=True)
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def get(path):
    time.sleep(0.7)
    req=urllib.request.Request('https://api.contexto.me/machado/en/'+path,headers=UA)
    try:
        r=urllib.request.urlopen(req,timeout=25); return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,None
    except Exception as ex: return None,{'exc':repr(ex)[:80]}
bins=[(0,1000),(1000,5000),(5000,10000),(10000,20000),(20000,40000),(40000,80000),(80000,160000),(160000,len(F))]
res=[]
for a,b in bins:
    for w in random.sample(F[a:b],60):
        st,r=get(f'game/1500/{w}'); res.append(dict(bin=[a,b],word=w,status=st,resp=r))
    print('bin',a,b,flush=True)
    json.dump(res,open(os.path.join(SP,'api','vocab_probe.json'),'w'),ensure_ascii=False,indent=0)
acc={}
for x in res:
    if x['status']==200: acc[x['resp']['lemma']]=x['resp']['distance']
far=sorted(acc,key=lambda w:-acc[w])[:25]
print('far',[(w,acc[w]) for w in far[:10]],flush=True)
multi={}
for g in [0,500,1000,1250,1505]:
    for w in far:
        st,r=get(f'game/{g}/{w}')
        if st==200: multi[f'{g}|{w}']=r['distance']
    print('multi',g,max(v for k,v in multi.items() if k.startswith(f'{g}|')),flush=True)
# tip cap
lo,hi=500,1000
while hi-lo>1:
    mid=(lo+hi)//2; st,r=get(f'tip/1500/{mid}')
    if st==200: lo=mid
    else: hi=mid
print('tip cap max ok distance',lo,flush=True)
# consistency tip(d) -> lemma -> game(lemma)=d, top order
top=get('top/1500')[1]['words']; cons=[]
for d in [1,2,3,10,50,100,200,300,400,499,500,lo]:
    st,r=get(f'tip/1500/{d}'); st2,r2=get(f"game/1500/{r['lemma']}") if st==200 else (None,None)
    cons.append(dict(d=d,tip=r,game=r2,top_match=(top[d]==r['lemma']) if d<500 and st==200 else None))
print('consistency',all(c['game'] and c['game']['distance']==c['d'] for c in cons),[c['top_match'] for c in cons],flush=True)
top_uni=len(set(top))==len(top)
print('top unique',top_uni,flush=True)
json.dump(dict(res=res,multi=multi,tip_cap=lo,cons=cons),open(os.path.join(SP,'api','vocab_probe.json'),'w'),ensure_ascii=False,indent=0)
print('DONE',flush=True)
