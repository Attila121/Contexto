# Finer dating of ranking changes: sample archived responses per calendar month and compare with live, plus rank correlation.
import json,re,random,time,urllib.request,sys,os,gzip,collections
SP=sys.argv[1]; random.seed(77)
rows=[l.split() for l in open(os.path.join(SP,'wayback','api_en_cdx.txt')) if len(l.split())==2]
by=collections.defaultdict(list)
for ts,u in rows:
    m=re.match(r'https?://api\.contexto\.me(?::\d+)?/machado/en/game/(\d+)/([a-z]+)$',u)
    if m: by[ts[:6]].append((ts,u,int(m.group(1)),m.group(2)))
print({k:len(v) for k,v in sorted(by.items())},flush=True)
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def fetch(url,timeout=45):
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=timeout); b=r.read(); st=r.status
    except urllib.error.HTTPError as e:
        b=e.read(); st=e.code
    if b[:2]==b'\x1f\x8b': b=gzip.decompress(b)
    return st,b
out=[]; pth=os.path.join(SP,'api','wb_month.json')
for mon in sorted(by):
    if mon<'202211': continue
    v=by[mon]; random.shuffle(v); n=0
    for ts,u,g,w in v:
        if n>=(6 if mon>='202503' else 10): break
        a=None
        for k in range(3):
            try:
                st,b=fetch(f'https://web.archive.org/web/{ts}id_/{u}')
                if st==429: time.sleep(30*(k+1)); continue
                a=json.loads(b.decode('utf-8','replace')); break
            except Exception: time.sleep(10*(k+1))
        time.sleep(2.5)
        if not isinstance(a,dict) or 'distance' not in a: continue
        time.sleep(0.5)
        st,b=fetch(f'https://api.contexto.me/machado/en/game/{g}/{w}',25)
        try: l=json.loads(b.decode())
        except Exception: l={}
        if 'distance' not in l: continue
        n+=1
        rec=dict(ts=ts,mon=mon,game=g,word=w,arch=a['distance'],live=l['distance'],la=a.get('lemma'),ll=l.get('lemma'))
        out.append(rec); print(mon,g,w,a['distance'],l['distance'],a['distance']==l['distance'],flush=True)
    json.dump(out,open(pth,'w'),ensure_ascii=False,indent=0)
print('DONE',flush=True)
