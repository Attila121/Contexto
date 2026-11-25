# Which GloVe 6B dimension reproduces the paper's Figure 2 cosines? And what token filter yields 317,756?
import zipfile,sys,io,re
import numpy as np
z=zipfile.ZipFile(sys.argv[1])
fig={'smile':.215,'eye':.352,'vision':.362,'look':.402,'emotion':.146,'happiness':.215,'animal':.085}
ranks={'look':15,'vision':34,'eye':43,'smile':206,'happiness':916,'emotion':3575,'animal':10867}
for dim in (50,100,200,300):
    words=[];rows=[]
    with z.open(f'glove.6B.{dim}d.txt') as f:
        for line in io.TextIOWrapper(f,encoding='utf-8',newline='\n'):
            p=line.rstrip('\n').split(' ')
            words.append(p[0]); rows.append(np.array(p[1:],dtype=np.float32))
    M=np.vstack(rows); del rows
    idx={w:i for i,w in enumerate(words)}
    N=M/np.linalg.norm(M,axis=1,keepdims=True)
    t=N[idx['mirror']]; sim=N@t
    print(f'--- {dim}d vocab={len(words)}')
    print(' cos:',{k:(round(float(sim[idx[k]]),3),v) for k,v in fig.items()})
    mae=np.mean([abs(float(sim[idx[k]])-v) for k,v in fig.items()]); print(' MAE',round(mae,4))
    # token-filter experiments for 317,756
    fl={'all':lambda w:True,'alpha_ascii':lambda w:re.fullmatch(r'[a-z]+',w) is not None,'isalpha':lambda w:w.isalpha(),'alnum':lambda w:w.isalnum(),'no_digit':lambda w:not any(c.isdigit() for c in w)}
    for name,fn in fl.items():
        mask=np.array([fn(w) for w in words]); o=np.argsort(-sim[mask]); w2=np.array(words,dtype=object)[mask][o]; pos={w:i+1 for i,w in enumerate(w2)}
        print(f' filter {name}: size={mask.sum()} ranks(paper)=',{k:(pos.get(k),ranks[k]) for k in ranks})
    if dim==300:
        np.savez_compressed(sys.argv[2],words=np.array(words),M=M)
    del M,N
