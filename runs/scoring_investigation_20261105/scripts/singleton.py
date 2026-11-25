# Lemma-confound-free identification test. A list word qualifies only if no OTHER vocabulary token can map to it under any
# WordNet POS lemmatization or simple inflection rule. Under a true (embedding, metric), order among such words must be exact.
import sys,os,json,re
SP=sys.argv[1]; EMB=sys.argv[2]; sys.argv=[sys.argv[0],SP]
sys.path.insert(0,os.path.join(SP,'scripts'))
import numpy as np
from scipy.stats import kendalltau
import nltk; nltk.data.path.insert(0,os.path.join(SP,'nltk_data'))
from nltk.stem import WordNetLemmatizer
from candidate import infl,load_lists
wl=WordNetLemmatizer()
z=np.load(EMB); words=[str(w) for w in z['words']]; M=z['M'].astype(np.float64)
E=dict(zip(words,M))
keep=[w for w in words if re.fullmatch(r'[a-z]+',w)]
# reverse map token -> possible lemmas
rev={}
for w in keep:
    for p in 'nvar':
        l=wl.lemmatize(w,p)
        if l!=w: rev.setdefault(l,set()).add(w)
def singleton(w):
    if w in rev: return False
    for f in infl(w,True):
        if f!=w and f in E: return False
    return True
old,new,live=load_lists()
def test(lst):
    t=lst[0]
    if t not in E: return None
    tv=E[t]; tn=np.linalg.norm(tv)
    U=[(i,w) for i,w in enumerate(lst[1:],1) if w in E and singleton(w)]
    if len(U)<15: return None
    ps=np.array([i for i,w in U]); V=np.vstack([E[w] for i,w in U])
    cos=V@tv/(np.linalg.norm(V,axis=1)*tn); dot=V@tv; euc=-np.linalg.norm(V-tv,axis=1)
    def disc(s):
        n=len(s);d=0
        for a in range(n):
            d+=int(((ps[a+1:]-ps[a])*(s[a]-s[a+1:])<0).sum())
        return d,n*(n-1)//2
    return dict(n=len(U),cos=float(kendalltau(ps,-cos).statistic),dot=float(kendalltau(ps,-dot).statistic),euc=float(kendalltau(ps,-euc).statistic),disc_cos=disc(cos)[0],pairs=disc(cos)[1])
out={}
for era,lists in (('old',old),('new',new),('live',live)):
    R=[test(v) for v in lists.values()]; R=[r for r in R if r]
    if not R: print(era,'no lists'); continue
    print(os.path.basename(EMB).ljust(30),era.ljust(5),'lists',len(R),'avg U',round(np.mean([r['n'] for r in R]),1),'tau cos mean',round(np.mean([r['cos'] for r in R]),4),'min',round(min(r['cos'] for r in R),4),'max',round(max(r['cos'] for r in R),4),'| dot',round(np.mean([r['dot'] for r in R]),3),'euc',round(np.mean([r['euc'] for r in R]),3),'| discordant pairs',sum(r['disc_cos'] for r in R),'/',sum(r['pairs'] for r in R),flush=True)
    out[era]=R
json.dump(out,open(os.path.join(SP,'api','singleton_'+os.path.basename(EMB).replace('.npz','')+'.json'),'w'),indent=0)
