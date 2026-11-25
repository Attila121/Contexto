import json,re,time,urllib.request,gzip,sys,os
SP=sys.argv[1]
rows=[l.split() for l in open(os.path.join(SP,'wayback','api_en_cdx.txt')) if len(l.split())==2]
tops=[]
for ts,u in rows:
    m=re.match(r'https?://api\.contexto\.me(?::\d+)?/machado/en/top/(\d+)$',u)
    if m: tops.append((ts,u,int(m.group(1))))
out={}
for ts,u,g in tops:
    for a in range(4):
        try:
            r=urllib.request.urlopen(urllib.request.Request(f'https://web.archive.org/web/{ts}id_/{u}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=50); b=r.read()
            if b[:2]==b'\x1f\x8b': b=gzip.decompress(b)
            out[f'{ts}|{g}']=json.loads(b.decode('utf-8','replace')).get('words'); print(ts,g,len(out[f'{ts}|{g}']),out[f'{ts}|{g}'][:5],flush=True); break
        except Exception as e:
            print('ERR',ts,g,repr(e)[:80],flush=True); time.sleep(15*(a+1))
    time.sleep(4)
    json.dump(out,open(os.path.join(SP,'api','arch_tops.json'),'w'),ensure_ascii=False,indent=0)
print('DONE')
