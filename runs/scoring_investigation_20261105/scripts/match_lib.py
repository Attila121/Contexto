import io,gzip,json,re,struct,sys,zipfile,os
import numpy as np
from scipy.stats import kendalltau,spearmanr
def needed(SP):
    L=json.load(open(os.path.join(SP,'api','top_lists.json'),encoding='utf-8'))
    A={}
    p=os.path.join(SP,'api','arch_tops.json')
    if os.path.exists(p): A=json.load(open(p,encoding='utf-8'))
    S=set()
    for v in list(L.values())+list(A.values()):
        if v: S.update(v)
    return L,A,S
def read_text_zip(path,member,S):
    out={}
    z=zipfile.ZipFile(path)
    with z.open(member) as f:
        first=True
        for raw in f:
            if first:
                first=False
                if raw.count(b' ')==1:  # fastText header
                    continue
            i=raw.find(b' ')
            w=raw[:i].decode('utf-8','replace')
            if w in S and w not in out:
                p=raw.decode('utf-8','replace').rstrip().split(' ')
                out[w]=np.array(p[-300:] if len(p)>300 else p[1:],dtype=np.float64)
    return out
def read_w2v_bin_gz(path,S):
    out={}
    with gzip.open(path,'rb') as f:
        n,d=map(int,f.readline().split()); sz=4*d
        for _ in range(n):
            ch=[]
            while True:
                c=f.read(1)
                if c==b' ': break
                if c!=b'\n': ch.append(c)
            w=b''.join(ch).decode('utf-8','replace')
            v=f.read(sz)
            if w in S: out[w]=np.frombuffer(v,dtype=np.float32).astype(np.float64)
    return out
def evaluate(E,word_list):
    t=word_list[0]
    if t not in E: return None
    idx=[i for i,w in enumerate(word_list[1:],1) if w in E]
    if len(idx)<20: return None
    V=np.vstack([E[word_list[i]] for i in idx]); tv=E[t]; pos=np.array(idx)
    cos=(V@tv)/(np.linalg.norm(V,axis=1)*np.linalg.norm(tv)); dot=V@tv; euc=-np.linalg.norm(V-tv,axis=1)
    res=dict(cover=len(idx)/(len(word_list)-1))
    for name,s in (('cos',cos),('dot',dot),('euc',euc)):
        res['tau_'+name]=float(kendalltau(pos,-s).statistic); res['rho_'+name]=float(spearmanr(pos,-s).statistic)
    # exact order on first 20 covered neighbours, cosine
    o=np.argsort(-cos); res['first20_exact']=int(np.sum(np.argsort(pos)[:20]==o[:20]))
    return res
def summarize(name,E,L,A):
    def agg(lists):
        R=[evaluate(E,v) for v in lists if v]; R=[r for r in R if r]
        if not R: return None
        k=R[0].keys()
        return {x:round(float(np.mean([r[x] for r in R])),3) for x in k}|{'n_lists':len(R),'min_tau_cos':round(min(r['tau_cos'] for r in R),3),'max_tau_cos':round(max(r['tau_cos'] for r in R),3)}
    return {'embedding':name,'vocab_found':len(E),'live':agg(list(L.values())),'archived':agg(list(A.values()))}
