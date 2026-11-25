# Compare archived official API responses (Wayback) to live responses. Read-only.
import json,re,random,time,urllib.request,sys,os,gzip,collections
SP=sys.argv[1]; random.seed(20261104)
rows=[l.split() for l in open(os.path.join(SP,'wayback','api_en_cdx.txt')) if len(l.split())==2]
games=[];tops=[]
for ts,u in rows:
    m=re.match(r'https?://api\.contexto\.me(?::\d+)?/machado/en/(\w+)/(\d+)(?:/(.*))?$',u)
    if not m: continue
    if m.group(1)=='game' and m.group(3): games.append((ts,u,int(m.group(2)),m.group(3)))
    if m.group(1)=='top': tops.append((ts,u,int(m.group(2))))
by=collections.defaultdict(list)
for g in games: by[g[0][:4]].append(g)
want={'2022':30,'2023':40,'2024':25,'2025':25,'2026':30}
sample=[]
for y,n in want.items():
    random.shuffle(by[y]); sample+=by[y][:n]
UA={'User-Agent':'Mozilla/5.0 (research-readonly)','Accept-Encoding':'gzip'}
def fetch(url,timeout=45):
    req=urllib.request.Request(url,headers=UA)
    try:
        r=urllib.request.urlopen(req,timeout=timeout); b=r.read(); st=r.status
    except urllib.error.HTTPError as e:
        b=e.read(); st=e.code
    if b[:2]==b'\x1f\x8b': b=gzip.decompress(b)
    return st,b
def wb(ts,u):
    for a in range(4):
        try:
            st,b=fetch(f'https://web.archive.org/web/{ts}id_/{u}')
            if st==429: time.sleep(30*(a+1)); continue
            return st,json.loads(b.decode('utf-8','replace'))
        except Exception as e:
            time.sleep(12*(a+1)); err=repr(e)[:100]
    return None,None
def live(path):
    time.sleep(0.7)
    st,b=fetch('https://api.contexto.me/machado/en/'+path,25)
    try: return st,json.loads(b.decode())
    except Exception: return st,None
out={'game':[],'top':[]}
pth=os.path.join(SP,'api','wb_drift.json')
for ts,u,g in tops:
    st,a=wb(ts,u); time.sleep(3)
    sl,l=live(f'top/{g}')
    aw=(a or {}).get('words') if isinstance(a,dict) else None; lw=(l or {}).get('words') if isinstance(l,dict) else None
    same=aw==lw if aw and lw else None
    fd=None
    if aw and lw and not same:
        fd=next((i for i,(x,y) in enumerate(zip(aw,lw)) if x!=y),None)
    rec=dict(ts=ts,game=g,n_archived=len(aw) if aw else None,n_live=len(lw) if lw else None,identical=same,first_diff=fd,target=lw[0] if lw else None)
    out['top'].append(rec); print('TOP',rec,flush=True); json.dump(out,open(pth,'w'),ensure_ascii=False)
for ts,u,g,w in sample:
    st,a=wb(ts,u); time.sleep(3)
    sl,l=live(f'game/{g}/{w}')
    rec=dict(ts=ts,game=g,word=w,arch_status=st,arch=a,live_status=sl,live=l,same=(a==l) if a is not None and l is not None else None,
             same_dist=(a.get('distance')==l.get('distance')) if isinstance(a,dict) and isinstance(l,dict) else None,
             same_lemma=(a.get('lemma')==l.get('lemma')) if isinstance(a,dict) and isinstance(l,dict) else None)
    out['game'].append(rec); print('GAME',ts[:8],g,w,(a or {}).get('distance') if isinstance(a,dict) else a,(l or {}).get('distance') if isinstance(l,dict) else l,rec['same_dist'],flush=True)
    json.dump(out,open(pth,'w'),ensure_ascii=False)
print('DONE',flush=True)
