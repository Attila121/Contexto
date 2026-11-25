import sys,os,json,collections,time,urllib.request
SP=sys.argv[1]; sys.argv=[sys.argv[0],SP]
sys.path.insert(0,os.path.join(SP,'scripts'))
import numpy as np
from scipy.stats import kendalltau
from candidate import infl
from match_lib import read_text_zip
S=json.load(open(os.path.join(SP,'api','switch.json'),encoding='utf-8'))
games=sorted({x['game'] for x in S})
tp=os.path.join(SP,'api','switch_targets.json')
T=json.load(open(tp)) if os.path.exists(tp) else {}
for g in games:
    if str(g) in T: continue
    time.sleep(1.5)
    T[str(g)]=json.loads(urllib.request.urlopen(urllib.request.Request(f'https://api.contexto.me/machado/en/top/{g}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=30).read().decode())['words'][0]
json.dump(T,open(tp,'w'))
need=set(T.values())
for x in S:
    for w in {x['lemma'],x['word']}:
        if w: need|=infl(w,True)
E6=read_text_zip(os.path.join(SP,'vec','glove.6B.zip'),'glove.6B.300d.txt',need)
E42=read_text_zip(os.path.join(SP,'vec','glove.42B.300d.zip'),'glove.42B.300d.txt',need)
print('vectors',len(E6),len(E42),flush=True)
def best(E,t,w):
    fs=[f for f in infl(w,True) if f in E]
    if not fs or t not in E: return None
    tv=E[t]; return max(float(E[f]@tv/(np.linalg.norm(E[f])*np.linalg.norm(tv))) for f in fs)
gr=collections.defaultdict(dict)
for x in S:
    gr[(x['game'],x['date'],x['tag'])][x['lemma'] or x['word']]=x['dist']
print('game date       target        n  tau_6B  tau_42B  era-call')
rows=[]
for (g,d,tag),m in sorted(gr.items(),key=lambda k:(k[0][1],k[0][0])):
    t=T[str(g)]
    a=[(dist,best(E6,t,w),best(E42,t,w)) for w,dist in m.items() if dist>0]
    a=[r for r in a if r[1] is not None and r[2] is not None]
    if len(a)<4: continue
    d_=[r[0] for r in a]
    t6=float(kendalltau(d_,[-r[1] for r in a]).statistic); t42=float(kendalltau(d_,[-r[2] for r in a]).statistic)
    call='OLD-6B' if t6>0.8 and t6>t42+0.1 else ('NEW' if t42>=t6-0.02 else 'mixed')
    rows.append(dict(game=g,date=d,tag=tag,target=t,n=len(a),tau6=round(t6,3),tau42=round(t42,3),call=call))
    print(g,d,t.ljust(13),str(len(a)).rjust(3),f'{t6:7.3f} {t42:7.3f}  {call}  {tag}',flush=True)
json.dump(rows,open(os.path.join(SP,'api','switch_an.json'),'w'),indent=0)
