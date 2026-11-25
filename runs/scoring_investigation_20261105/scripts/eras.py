import sys,os,json
sys.path.insert(0,os.path.join(sys.argv[1],'scripts'))
from match_lib import *
import urllib.request,time
SP=sys.argv[1]
A=json.load(open(os.path.join(SP,'api','arch_tops.json'),encoding='utf-8'))
L=json.load(open(os.path.join(SP,'api','top_lists.json'),encoding='utf-8'))
# fetch live lists for archived games (for era comparison), once
Lp=os.path.join(SP,'api','live_for_arch.json')
if os.path.exists(Lp): LA=json.load(open(Lp,encoding='utf-8'))
else:
    LA={}
    for k in A:
        g=k.split('|')[1]
        time.sleep(0.7)
        LA[g]=json.loads(urllib.request.urlopen(urllib.request.Request(f'https://api.contexto.me/machado/en/top/{g}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=25).read().decode())['words']
    json.dump(LA,open(Lp,'w'),ensure_ascii=False,indent=0)
z=np.load(os.path.join(SP,'vec','x','glove6B300.npz')); words=z['words']; M=z['M'].astype(np.float64); idx={str(w):i for i,w in enumerate(words)}
def E_for(lst): return {w:M[idx[w]] for w in lst if w in idx}
print('ts        game target         overlap500 tau_arch_vs_live | 6B tau(arch) | 6B tau(live same game) | first20 arch | first8 arch || first8 live')
for k,a in sorted(A.items()):
    ts,g=k.split('|'); l=LA[g]
    common=[w for w in a if w in set(l)]
    ov=len(common)
    pa=[a.index(w) for w in common]; pl=[l.index(w) for w in common]
    tau=float(kendalltau(pa,pl).statistic)
    ra=evaluate(E_for(a),a); rl=evaluate(E_for(l),l)
    print(ts[:8],g.rjust(4),a[0].ljust(14),str(ov).rjust(4),f"{tau:7.3f}",'|',f"{ra['tau_cos']:.3f}/{ra['tau_dot']:.3f}" if ra else None,'|',f"{rl['tau_cos']:.3f}" if rl else None,'|',ra['first20_exact'] if ra else None,'|',a[1:8],'||',l[1:8])
