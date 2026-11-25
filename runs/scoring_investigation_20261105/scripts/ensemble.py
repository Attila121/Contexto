# Unweighted combinations of the tested embeddings against the live lists. No fitted parameters.
import sys,os,json,itertools
SP=sys.argv[1]; sys.argv=[sys.argv[0],SP]
sys.path.insert(0,os.path.join(SP,'scripts'))
import numpy as np
from scipy.stats import kendalltau,rankdata
from candidate import infl,load_lists
names=['glove.6B.300d','glove.42B.300d','glove.840B.300d','fasttext.crawl.300d','glove.twitter.27B.200d']
EM={}
for n in names:
    z=np.load(os.path.join(SP,'vec','x',f'{n}_needed.npz')); EM[n]=dict(zip([str(w) for w in z['words']],z['M'].astype(np.float64)))
old,new,live=load_lists()
def scores(E,lst):
    t=lst[0]
    if t not in E: return {}
    tv=E[t]; tn=np.linalg.norm(tv); out={}
    for w in lst[1:]:
        fs=[f for f in infl(w,True) if f in E]
        if fs: out[w]=max(float(E[f]@tv/(np.linalg.norm(E[f])*tn)) for f in fs)
    return out
S={k:{n:scores(EM[n],v) for n in names} for k,v in live.items()}
res=[]
for r in range(1,len(names)+1):
    for c in itertools.combinations(names,r):
        for mode in ('rank-avg','z-avg'):
            taus=[]
            for k,lst in live.items():
                common=[w for w in lst[1:] if all(w in S[k][n] for n in c)]
                if len(common)<50: continue
                M=np.array([[S[k][n][w] for w in common] for n in c])
                if mode=='rank-avg': s=np.mean([rankdata(x) for x in M],axis=0)
                else: s=np.mean([(x-x.mean())/x.std() for x in M],axis=0)
                pos=[lst.index(w) for w in common]
                taus.append(float(kendalltau(pos,-s).statistic))
            res.append((round(float(np.mean(taus)),3),round(min(taus),3),round(max(taus),3),mode,'+'.join(x.split('.')[1] if x.startswith('glove') else 'crawl' for x in c)))
res.sort(reverse=True)
print('best unweighted combinations on live lists (mean tau, min, max):')
for x in res[:8]: print(' ',x)
print('singles:',[x for x in res if '+' not in x[4] and x[3]=='z-avg'])
json.dump(res,open(os.path.join(SP,'api','ensemble.json'),'w'),indent=0)
