import sys,re,time,urllib.request,json,os
SP=sys.argv[1]; rows=[l.split() for l in open(os.path.join(SP,'wayback','js_cdx.txt')) if l.strip()]
seen={}
for r in rows:
    ts,u=r[0],r[1]
    if '__/auth' in u: continue
    name=u.rsplit('/',1)[-1]
    if name not in seen or ts<seen[name][0]: seen[name]=(ts,u)
items=sorted(seen.values())
print(len(items),flush=True)
out=os.path.join(SP,'wayback','bundles'); os.makedirs(out,exist_ok=True)
log=open(os.path.join(SP,'wayback','bundles_log.jsonl'),'a',encoding='utf-8')
for ts,u in items:
    name=ts+'_'+u.rsplit('/',1)[-1]; p=os.path.join(out,name)
    if os.path.exists(p) and os.path.getsize(p)>0: continue
    url=f'https://web.archive.org/web/{ts}id_/{u}'
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (research-readonly)','Accept-Encoding':'identity'})
            b=urllib.request.urlopen(req,timeout=60).read()
            open(p,'wb').write(b); log.write(json.dumps({'ts':ts,'url':u,'bytes':len(b)})+'\n'); log.flush(); print(ts,u,len(b),flush=True)
            break
        except Exception as e:
            print('ERR',u,repr(e)[:120],flush=True); time.sleep(20*(attempt+1))
    time.sleep(3)
print('DONE',flush=True)
