# Replays previously recorded (guess -> displayed rank) pairs in a fresh random order, cookie-less. Reads records only.
import urllib.parse
import json,glob,os,random,time,urllib.request,datetime,collections,sys
RUNS=sys.argv[1]; random.seed(4242)
EN0=datetime.date(2022,9,18)
pairs=[];inv=[]
for ev in glob.glob(os.path.join(RUNS,'**','events.jsonl'),recursive=True):
    if 'scoring_inspection' in ev: continue
    start=None
    for line in open(ev,encoding='utf-8'):
        try:e=json.loads(line)
        except Exception: continue
        if e.get('event')=='start': start=e
        if e.get('event')=='feedback' and start:
            d=start.get('puzzle') or ''
            try: g=(datetime.date.fromisoformat(d)-EN0).days
            except Exception: continue
            ts=e.get('timestamp','')[:10]
            if e.get('feedback')=='rank' and isinstance(e.get('rank'),int): pairs.append((g,e['guess'],e['rank'],ts,os.path.relpath(ev,RUNS).split(os.sep)[0]))
            elif e.get('feedback')!='quit' and e.get('guess'): inv.append((g,e['guess'],e.get('feedback'),ts))
print('recorded ranked',len(pairs),'invalid/dup',len(inv))
print('dates',collections.Counter(p[3] for p in pairs))
by=collections.defaultdict(list)
for p in pairs: by[p[3]].append(p)
samp=[]
for k,v in by.items():
    random.shuffle(v); samp+=v[:(90 if k.startswith('2026-11') else 45)]
random.shuffle(samp)
res=[]
for g,w,r,ts,run in samp:
    time.sleep(0.7)
    req=urllib.request.Request(f'https://api.contexto.me/machado/en/game/{g}/{urllib.parse.quote(w)}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'})
    try:
        x=urllib.request.urlopen(req,timeout=25); b=json.loads(x.read().decode()); cookie=x.headers.get('Set-Cookie')
    except urllib.error.HTTPError as e:
        b={'err':e.code}; cookie=None
    res.append(dict(game=g,word=w,rec_rank=r,rec_date=ts,live=b,match=(b.get('distance',-99)+1==r),setcookie=cookie))
c=collections.Counter((x['rec_date'],x['match']) for x in res); print(sorted(c.items()))
print('Set-Cookie seen:',any(x['setcookie'] for x in res))
print('mismatches:',[ (x['game'],x['word'],x['rec_rank'],x['live']) for x in res if not x['match']][:15])
# Order independence: fixed triples in opposite order and repeated
tests=['apple','bridge','plum','window']
A={};B={}
for w in tests:
    time.sleep(0.7); A[w]=json.loads(urllib.request.urlopen(urllib.request.Request(f'https://api.contexto.me/machado/en/game/1500/{w}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=25).read().decode())
for w in reversed(tests):
    time.sleep(0.7); B[w]=json.loads(urllib.request.urlopen(urllib.request.Request(f'https://api.contexto.me/machado/en/game/1500/{w}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=25).read().decode())
print('order swap identical:',A==B,A)
json.dump(res,open(sys.argv[2],'w'),ensure_ascii=False,indent=0)
