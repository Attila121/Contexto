import sys,os,json,re
SP=sys.argv[1]; sys.argv=[sys.argv[0],SP]
sys.path.insert(0,os.path.join(SP,'scripts'))
import numpy as np
from scipy.stats import kendalltau
import nltk; nltk.data.path.insert(0,os.path.join(SP,'nltk_data'))
from nltk.stem import WordNetLemmatizer
wl=WordNetLemmatizer()
z=np.load(os.path.join(SP,'vec','x','glove6B300.npz')); words=[str(w) for w in z['words']]; M=z['M'].astype(np.float64)
keep=[i for i,w in enumerate(words) if re.fullmatch(r'[a-z]+',w)]
W=[words[i] for i in keep]; N=M[keep]; N=N/np.linalg.norm(N,axis=1,keepdims=True); pos={w:i for i,w in enumerate(W)}
del M
def L_n(w): return wl.lemmatize(w,'n')
def L_nv(w):
    a=wl.lemmatize(w,'n')
    return a if a!=w else wl.lemmatize(w,'v')
def L_vn(w):
    a=wl.lemmatize(w,'v')
    return a if a!=w else wl.lemmatize(w,'n')
def L_nva(w):
    for p in 'nva':
        a=wl.lemmatize(w,p)
        if a!=w: return a
    return w
def L_nvar(w):
    for p in 'nvar':
        a=wl.lemmatize(w,p)
        if a!=w: return a
    return w
def L_vna(w):
    for p in 'vna':
        a=wl.lemmatize(w,p)
        if a!=w: return a
    return w
LEM={'wn:n':L_n,'wn:n>v':L_nv,'wn:v>n':L_vn,'wn:n>v>a':L_nva,'wn:n>v>a>r':L_nvar,'wn:v>n>a':L_vna}
A=json.load(open(os.path.join(SP,'api','arch_tops.json'),encoding='utf-8'))
old={k:v for k,v in sorted(A.items()) if k.split('|')[0]<'20230208'}
LA=json.load(open(os.path.join(SP,'api','live_for_arch.json'),encoding='utf-8'))
L=json.load(open(os.path.join(SP,'api','top_lists.json'),encoding='utf-8'))
TOPK=60000
res={}
for lname,fn in LEM.items():
    cache={}
    def lem(w):
        if w not in cache: cache[w]=fn(w)
        return cache[w]
    taus=[];exact=[];nprefix=[]
    for k,lst in old.items():
        t=lst[0]; sim=N@N[pos[t]]
        o=np.argsort(-sim)[:TOPK]
        best={}
        for i in o:
            l=lem(W[i])
            if l not in best: best[l]=float(sim[i])
        have=[(p,w) for p,w in enumerate(lst[1:],1) if w in best]
        ps=[p for p,w in have]; ss=[-best[w] for p,w in have]
        tau=float(kendalltau(ps,ss).statistic); taus.append(tau)
        # exact sequence within listed words
        ordered=sorted(have,key=lambda x:-best[x[1]]); ex=sum(a[0]==b[0] for a,b in zip(have,ordered)); exact.append(ex/len(have))
    print(lname.ljust(12),'mean tau',round(np.mean(taus),4),'min',round(min(taus),4),'max',round(max(taus),4),'exact pos frac',round(float(np.mean(exact)),3),'coverage',len(have),flush=True)
    res[lname]=dict(taus=[round(t,4) for t in taus],exact=[round(e,3) for e in exact])
json.dump(res,open(os.path.join(SP,'api','old_exact.json'),'w'),indent=0)
