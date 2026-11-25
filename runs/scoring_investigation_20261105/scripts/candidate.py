# Usage: candidate.py SP name kind path member   -- evaluates one embedding against all eras, saves vectors for needed words
import sys,os,json
SP=sys.argv[1]
sys.path.insert(0,os.path.join(SP,'scripts'))
from match_lib import *
V_='aeiou'
def infl(w,comp=False):
    F={w,w+'s',w+'es',w+'ed',w+'d',w+'ing'}
    if w.endswith('y') and len(w)>2 and w[-2] not in V_: F|={w[:-1]+'ies',w[:-1]+'ied'}
    if w.endswith('e'): F|={w[:-1]+'ing'}
    if len(w)>2 and w[-1] not in V_+'wxy' and w[-2] in V_ and w[-3] not in V_: F|={w+w[-1]+'ing',w+w[-1]+'ed'}
    if w.endswith('f'): F|={w[:-1]+'ves'}
    if w.endswith('fe'): F|={w[:-2]+'ves'}
    if comp:
        F|={w+'er',w+'est',w+'r',w+'st'}
        if w.endswith('y') and len(w)>2: F|={w[:-1]+'ier',w[:-1]+'iest'}
        if len(w)>2 and w[-1] not in V_+'wxy' and w[-2] in V_ and w[-3] not in V_: F|={w+w[-1]+'er',w+w[-1]+'est'}
    return F
def load_lists():
    A=json.load(open(os.path.join(SP,'api','arch_tops.json'),encoding='utf-8'))
    LA=json.load(open(os.path.join(SP,'api','live_for_arch.json'),encoding='utf-8'))
    L=json.load(open(os.path.join(SP,'api','top_lists.json'),encoding='utf-8'))
    old={k:v for k,v in A.items() if k.split('|')[0]<'20230208'}
    new={k:v for k,v in A.items() if k.split('|')[0]>='20230208'}
    live={('L'+g):v for g,v in L.items()}
    for g,v in LA.items(): live.setdefault('L'+g,v)
    return old,new,live
def score(E,lst,fset,metric):
    t=lst[0]
    if t not in E: return None
    tv=E[t]; tn=np.linalg.norm(tv)
    idx=[];sc=[]
    for i,w in enumerate(lst[1:],1):
        fs=[f for f in fset(w) if f in E]
        if not fs: continue
        V=np.vstack([E[f] for f in fs])
        if metric=='cos': s=(V@tv/(np.linalg.norm(V,axis=1)*tn)).max()
        elif metric=='dot': s=(V@tv).max()
        else: s=(-np.linalg.norm(V-tv,axis=1)).max()
        idx.append(i);sc.append(float(s))
    if len(idx)<20: return None
    return float(kendalltau(idx,-np.array(sc)).statistic),len(idx)/(len(lst)-1)
def table(name,E,detail=False):
    old,new,live=load_lists(); rows=[]
    fsets={'lemma-vector':lambda w:{w},'inflections':lambda w:infl(w),'inflect+comparative':lambda w:infl(w,True)}
    for era,lists in (('old (<2023-02-08)',old),('2023-02-08..2024',new),('live 2026',live)):
        for fn,fs in fsets.items():
            for metric in ('cos','dot','euc'):
                if metric!='cos' and fn!='inflections': continue
                r=[score(E,v,fs,metric) for v in lists.values()]; r=[x for x in r if x]
                if not r: continue
                t=[x[0] for x in r]; cov=np.mean([x[1] for x in r])
                rows.append(dict(embedding=name,era=era,forms=fn,metric=metric,n=len(r),mean=round(float(np.mean(t)),3),min=round(min(t),3),max=round(max(t),3),cover=round(float(cov),3)))
                print(name.ljust(20),era.ljust(18),fn.ljust(20),metric,'n',len(r),'tau mean',f"{np.mean(t):.3f}",'min',f"{min(t):.3f}",'max',f"{max(t):.3f}",'cov',f"{cov:.2f}",flush=True)
    return rows
if __name__=='__main__':
    name,kind,path=sys.argv[2],sys.argv[3],sys.argv[4]; member=sys.argv[5] if len(sys.argv)>5 else None
    old,new,live=load_lists()
    S=set()
    for d in (old,new,live):
        for v in d.values():
            for w in v: S|=infl(w,True)
    E=read_text_zip(path,member,S) if kind=='zip' else read_w2v_bin_gz(path,S)
    print(name,'loaded',len(E),'of',len(S),flush=True)
    rows=table(name,E)
    json.dump(rows,open(os.path.join(SP,'api',f'cand_{name}.json'),'w'),indent=0)
    np.savez_compressed(os.path.join(SP,'vec','x',f'{name}_needed.npz'),words=np.array(list(E.keys())),M=np.vstack(list(E.values())))
