# Re-scores the study's recorded guesses in the replicated paper environment (GloVe 6B 300d, cosine, ^[a-z]+$). Read-only on records.
import sys,os,json,re,math,glob
import numpy as np
from scipy.stats import spearmanr
SP,RUN=sys.argv[1],sys.argv[2]
z=np.load(os.path.join(SP,'vec','x','glove6B300.npz')); words=[str(w) for w in z['words']]; M=z['M'].astype(np.float32)
keep=[i for i,w in enumerate(words) if re.fullmatch(r'[a-z]+',w)]; W=[words[i] for i in keep]; N=M[keep]; N/=np.linalg.norm(N,axis=1,keepdims=True); pos={w:i for i,w in enumerate(W)}
del M
L=json.load(open(os.path.join(SP,'api','top_lists.json'),encoding='utf-8'))
import datetime
EN0=datetime.date(2022,9,18)
tot=[];rows=[]
C_paper=len(W)
for d in sorted(os.listdir(RUN)):
    ev=os.path.join(RUN,d,'events.jsonl')
    if not os.path.exists(ev): continue
    g=(datetime.date.fromisoformat(d)-EN0).days; t=L[str(g)][0]
    sim=N@N[pos[t]]; o=np.argsort(-sim); rk=np.empty(len(o),dtype=np.int64); rk[o]=np.arange(1,len(o)+1)
    ctx=[];pap=[];oov=[];seq=[];attempts=0;solved_ctx=False;words_seen=[]
    for line in open(ev,encoding='utf-8'):
        e=json.loads(line)
        if e.get('event')!='feedback' or e.get('feedback')=='quit': continue
        attempts+=1
        if e['feedback']=='rank':
            w=e['guess'].lower(); r=e['rank']
            if r==1: solved_ctx=True
            pr=int(rk[pos[w]]) if w in pos else None
            ctx.append(r);pap.append(pr);seq.append((w,r,pr));words_seen.append(w)
            if pr is None: oov.append(w)
    pairs=[(a,b) for a,b in zip(ctx,pap) if b]
    rho=spearmanr([a for a,b in pairs],[b for a,b in pairs]).statistic if len(pairs)>2 else float('nan')
    # direction agreement on consecutive transitions
    tr=[x for x in seq if x[2]]
    same=sum(((a[1]<b[1])==(a[2]<b[2])) for a,b in zip(tr,tr[1:])); n=len(tr)-1
    best_c=min(ctx); bp=min(b for a,b in pairs)
    tot.append(dict(date=d,game=g,target=t,attempts=attempts,ranked=len(ctx),rho=round(float(rho),3),dir_agree=round(same/n,3) if n>0 else None,n_tr=n,oov=oov,best_ctx=best_c,best_paper=bp,solved_ctx=solved_ctx,paper_oov=len(oov)))
    print(tot[-1],flush=True)
    rows+= [dict(date=d,target=t,word=w,ctx=r,paper=p) for w,r,p in seq]
R=[x for x in rows if x['paper']]
print('POOLED n',len(R),'spearman',round(float(spearmanr([x['ctx'] for x in R],[x['paper'] for x in R]).statistic),3))
print('mean per-game rho',round(float(np.mean([t['rho'] for t in tot])),3),'mean dir agree (weighted)',round(sum(t['dir_agree']*t['n_tr'] for t in tot)/sum(t['n_tr'] for t in tot),3))
print('max ctx rank',max(x['ctx'] for x in R),'max paper rank',max(x['paper'] for x in R))
print('median ratio paper/ctx',round(float(np.median([x['paper']/x['ctx'] for x in R])),2))
big=sorted(R,key=lambda x:-abs(math.log(x['paper']/x['ctx'])))[:12]; print('largest disagreements',[(x['target'],x['word'],x['ctx'],x['paper']) for x in big])
json.dump(dict(games=tot,rows=rows),open(os.path.join(SP,'api','counterfactual.json'),'w'),ensure_ascii=False,indent=0)
