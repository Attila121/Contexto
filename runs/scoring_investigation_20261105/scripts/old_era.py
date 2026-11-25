import sys,os,json,zipfile,io
sys.path.insert(0,os.path.join(sys.argv[1],'scripts'))
from match_lib import *
from forms import forms
SP=sys.argv[1]
A=json.load(open(os.path.join(SP,'api','arch_tops.json'),encoding='utf-8'))
LA=json.load(open(os.path.join(SP,'api','live_for_arch.json'),encoding='utf-8'))
old={k:v for k,v in A.items() if k.split('|')[0]<'20230208'}
new={k:v for k,v in A.items() if k.split('|')[0]>='20230208'}
base=set(w for v in A.values() for w in v)|set(w for v in LA.values() for w in v)
S=set()
for w in base: S|=forms(w)
def ev(E,lst,best):
    t=lst[0]
    if t not in E: return None
    T=[f for f in forms(t) if f in E]
    idx=[];sc=[]
    tv=E[t]/np.linalg.norm(E[t])
    for i,w in enumerate(lst[1:],1):
        fs=[f for f in (forms(w) if best else [w]) if f in E]
        if not fs: continue
        s=max(float(E[f]@tv/np.linalg.norm(E[f])) for f in fs)
        idx.append(i);sc.append(s)
    return float(kendalltau(idx,-np.array(sc)).statistic),len(idx)/(len(lst)-1)
results={}
def run(name,E):
    for era,lists in (('old<2023-02-08',old),('new>=2023-02-08',new),('live(same games)',{k:LA[k.split('|')[1]] for k in A})):
        for best in (False,True):
            r=[ev(E,v,best) for v in lists.values()]; r=[x for x in r if x]
            taus=[x[0] for x in r]
            print(name.ljust(22),era.ljust(18),'bestform' if best else 'lemmaVec','n',len(r),'mean tau',round(float(np.mean(taus)),3),'min',round(min(taus),3),'max',round(max(taus),3),flush=True)
            results[f'{name}|{era}|{"best" if best else "lemma"}']=taus
for dim in (50,100,200,300):
    E=read_text_zip(os.path.join(SP,'vec','glove.6B.zip'),f'glove.6B.{dim}d.txt',S)
    if dim==50: print('found',len(E))
    run(f'glove.6B.{dim}d',E)
