import json,time,urllib.request,urllib.parse,sys,os,re,collections
SP=sys.argv[1]
def get(path):
    time.sleep(0.8)
    try:
        r=urllib.request.urlopen(urllib.request.Request('https://api.contexto.me/machado/en/'+path,headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=25); return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,None
A=json.load(open(os.path.join(SP,'api','arch_tops.json'),encoding='utf-8')); LA=json.load(open(os.path.join(SP,'api','live_for_arch.json'),encoding='utf-8'))
out={}
print('--- rejected-word classes (game 1500)')
for w in ['kill','murder','assault','tart','ginger','gun','war','death','die','bomb','weapon','blood','violence','attack','shoot','crime','drug','sex','hate','suicide','slave','cherry','peach','banana','tomorrow','today','now']:
    s,b=get(f'game/1500/{w}'); out[w]=(s,b); print(w,s,b.get('error') if isinstance(b,dict) and 'error' in b else b.get('distance') if isinstance(b,dict) else b,flush=True)
print('--- removed since archive: list words absent from live top (latest archived lists)')
rem={}
for k in sorted(A,key=lambda x:x)[-4:]:
    ts,g=k.split('|'); a=A[k]; l=set(LA[g])
    gone=[(i,w) for i,w in enumerate(a) if w not in l]
    rem[k]=[]
    for i,w in gone[:24]:
        s,b=get(f'game/{g}/{w}'); rem[k].append((i,w,s,b))
    print(k,a[0],'gone',len(gone)); print('   ',[(i,w,(b.get('error') or b.get('distance')) if isinstance(b,dict) else s) for i,w,s,b in rem[k]],flush=True)
json.dump(dict(classes=out,removed=rem),open(os.path.join(SP,'api','block.json'),'w'),ensure_ascii=False,indent=0)
