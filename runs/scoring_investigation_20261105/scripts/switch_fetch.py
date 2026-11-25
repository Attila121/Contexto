# Separates "switch by date" from "switch by game ID" using captures of the same game before/after Feb 7-8 2023.
import json,re,random,time,urllib.request,sys,os,gzip,collections
SP=sys.argv[1]; random.seed(99)
rows=[l.split() for l in open(os.path.join(SP,'wayback','api_en_cdx.txt')) if len(l.split())==2]
cap=collections.defaultdict(list)
for ts,u in rows:
    m=re.match(r'https?://api\.contexto\.me(?::\d+)?/machado/en/game/(\d+)/([a-z]+)$',u)
    if m: cap[(int(m.group(1)),ts[:8])].append((ts,u,m.group(2)))
want=[(131,'20230206',16),(131,'20230208',18),(135,'20230206',16),(135,'20230208',5),(135,'20230227',5),
      (136,'20230206',18),(136,'20230212',18),(136,'20230227',18),(139,'20230206',18),(139,'20230208',13),(139,'20230212',18),
      (142,'20230208',20),(143,'20230210',18),(148,'20230214',18),(107,'20230206',16),(120,'20230206',16),(70,'20221219',20)]
# old-ID, later captures grouped by month
late=collections.defaultdict(list)
for (g,d),v in cap.items():
    if g<=135 and '20230301'<=d<='20230630':
        for x in v: late[d[:6]].append((g,d,x))
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def fetch(ts,u):
    for k in range(4):
        try:
            r=urllib.request.urlopen(urllib.request.Request(f'https://web.archive.org/web/{ts}id_/{u}',headers=UA),timeout=45); b=r.read()
            if b[:2]==b'\x1f\x8b': b=gzip.decompress(b)
            return json.loads(b.decode('utf-8','replace'))
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(40*(k+1))
            else: return None
        except Exception: time.sleep(10*(k+1))
    return None
out=[]; p=os.path.join(SP,'api','switch.json')
def go(tag,g,d,items):
    for ts,u,w in items:
        a=fetch(ts,u); time.sleep(3)
        if isinstance(a,dict) and 'distance' in a: out.append(dict(tag=tag,game=g,date=d,ts=ts,word=w,dist=a['distance'],lemma=a.get('lemma')))
    print(tag,g,d,len(items),flush=True); json.dump(out,open(p,'w'),ensure_ascii=False,indent=0)
for g,d,n in want:
    v=cap.get((g,d),[]); random.shuffle(v); go('straddle',g,d,v[:n])
for mon,v in sorted(late.items()):
    random.shuffle(v); bygame=collections.defaultdict(list)
    for g,d,x in v[:60]: bygame[(g,d)].append(x)
    for (g,d),items in list(bygame.items()):
        if len(items)>=4: go('late_oldid',g,d,items[:14])
print('DONE',flush=True)
