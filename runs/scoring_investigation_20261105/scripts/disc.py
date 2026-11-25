import sys,os,json
SP=sys.argv[1]; sys.argv=[sys.argv[0],SP]
sys.path.insert(0,os.path.join(SP,'scripts'))
from candidate import *
z=np.load(os.path.join(SP,'vec','x','glove.6B.300d_needed.npz')); E={str(w):v.astype(np.float64) for w,v in zip(z['words'],z['M'])}
old,new,live=load_lists()
for k,lst in sorted(old.items())[:8]:
    t=lst[0]; tv=E[t]; tn=np.linalg.norm(tv); rows=[]
    for i,w in enumerate(lst[1:],1):
        fs=[f for f in infl(w,True) if f in E]
        best=max(fs,key=lambda f:E[f]@tv/(np.linalg.norm(E[f])*tn)); rows.append((i,w,best,float(E[best]@tv/(np.linalg.norm(E[best])*tn))))
    order=sorted(rows,key=lambda r:-r[3]); mp={r[1]:n+1 for n,r in enumerate(order)}
    disp=sorted(rows,key=lambda r:-abs(mp[r[1]]-r[0]))[:10]
    tau=kendalltau([r[0] for r in rows],[-r[3] for r in rows]).statistic
    n_exact=sum(mp[r[1]]==r[0] for r in rows)
    print(k,t,'tau',round(float(tau),4),'exact positions',n_exact,'/',len(rows))
    print('  worst (pos,word,bestform,modelpos):',[(r[0],r[1],r[2],mp[r[1]]) for r in disp])
