import sys,os,json
sys.path.insert(0,os.path.join(sys.argv[1],'scripts'))
from match_lib import *
SP=sys.argv[1]
L,A,S=needed(SP)
z=np.load(os.path.join(SP,'vec','x','glove6B300.npz'))
words=z['words']; M=z['M'].astype(np.float64)
idx={str(w):i for i,w in enumerate(words)}
E={w:M[idx[w]] for w in S if w in idx}
print(json.dumps(summarize('glove.6B.300d',E,L,A)))
# Demo replication: does our 6B/300d/^[a-z]+$ environment reproduce the public demo's ranks?
mask=np.array([re.fullmatch(r'[a-z]+',str(w)) is not None for w in words])
Wf=words[mask]; Mf=M[mask]; N=Mf/np.linalg.norm(Mf,axis=1,keepdims=True)
pos0={str(w):i for i,w in enumerate(Wf)}
def rankmap(t):
    sim=N@N[pos0[t]]; o=np.argsort(-sim); r=np.empty(len(o),int); r[o]=np.arange(1,len(o)+1); return r
r=rankmap('banana')
demo=json.load(open(os.path.join(SP,'api','wp_vs_ctx_banana.json'),encoding='utf-8'))
ok=bad=0; rows=[]
for x in demo:
    st,b=x['wordpolo']
    if isinstance(b,dict) and 'rank' in b and x['word'] in pos0:
        mine=int(r[pos0[x['word']]]); rows.append((x['word'],b['rank'],mine)); ok+=mine==b['rank']; bad+=mine!=b['rank']
print('demo exact matches',ok,'mismatch',bad,[t for t in rows if t[1]!=t[2]][:12])
print('demo-not-found words in env:',[x['word'] for x in demo if x['wordpolo'][0]==404 and x['word'] in pos0],[x['word'] for x in demo if x['wordpolo'][0]==404])
print('GloVe 6B top neighbours of pear (filtered):',[str(Wf[i]) for i in np.argsort(-(N@N[pos0['pear']]))[:30]])
print('Contexto top 30 of pear:',L['1500'][:30])
for g in ['1500','0','1505']:
    t=L[g][0]; rr=rankmap(t)
    print('game',g,t,'Contexto first 15 -> their paper-env rank:',[(w,int(rr[pos0[w]]) if w in pos0 else None) for w in L[g][1:16]])
