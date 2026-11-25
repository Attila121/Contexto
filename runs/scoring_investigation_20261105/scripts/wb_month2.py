# Continues the month-level archived-vs-live sampling from Nov 2023, tolerant of network errors, at a gentle rate.
import json,re,random,time,urllib.request,sys,os,gzip,collections
SP=sys.argv[1]; random.seed(78)
rows=[l.split() for l in open(os.path.join(SP,'wayback','api_en_cdx.txt')) if len(l.split())==2]
by=collections.defaultdict(list)
for ts,u in rows:
    m=re.match(r'https?://api\.contexto\.me(?::\d+)?/machado/en/game/(\d+)/([a-z]+)$',u)
    if m: by[ts[:6]].append((ts,u,int(m.group(1)),m.group(2)))
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def fetch(url,timeout=45):
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=timeout); b=r.read(); st=r.status
    except urllib.error.HTTPError as e:
        b=e.read(); st=e.code
    if b[:2]==b'\x1f\x8b': b=gzip.decompress(b)
    return st,b
out=[]; pth=os.path.join(SP,'api','wb_month2.json')
for mon in sorted(by):
    if mon<'202311': continue
    v=by[mon]; random.shuffle(v); n=0
    for ts,u,g,w in v:
        if n>=6: break
        a=None
        for k in range(3):
            try:
                st,b=fetch(f'https://web.archive.org/web/{ts}id_/{u}')
                if st==429: time.sleep(30*(k+1)); continue
                a=json.loads(b.decode('utf-8','replace')); break
            except Exception: time.sleep(10*(k+1))
        time.sleep(3)
        if not isinstance(a,dict) or 'distance' not in a: continue
        try:
            time.sleep(1.5); st,b=fetch(f'https://api.contexto.me/machado/en/game/{g}/{w}',25); l=json.loads(b.decode())
        except Exception as e:
            print('live error',repr(e)[:80],flush=True); time.sleep(20); continue
        if 'distance' not in l: continue
        n+=1
        out.append(dict(ts=ts,mon=mon,game=g,word=w,arch=a['distance'],live=l['distance'],la=a.get('lemma'),ll=l.get('lemma')))
        print(mon,g,w,a['distance'],l['distance'],a['distance']==l['distance'],flush=True)
    json.dump(out,open(pth,'w'),ensure_ascii=False,indent=0)
print('DONE',flush=True)
