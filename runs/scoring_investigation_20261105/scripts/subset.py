# Is Contexto's vocabulary a subset of GloVe 6B? Sample common web-corpus tokens absent from 6B and query the API. Control: tokens present in 6B at similar frequency rank in 42B.
import zipfile,re,random,json,time,sys,os,urllib.request
import numpy as np
SP=sys.argv[1]; random.seed(11)
b6=set(str(w) for w in np.load(os.path.join(SP,'vec','x','glove6B300.npz'))['words'])
z=zipfile.ZipFile(os.path.join(SP,'vec','glove.42B.300d.zip'))
absent=[];present=[]; n=0
with z.open('glove.42B.300d.txt') as f:
    for raw in f:
        i=raw.find(b' '); w=raw[:i].decode('utf-8','replace'); n+=1
        if re.fullmatch(r'[a-z]{3,}',w):
            (present if w in b6 else absent).append((n,w))
        if n>=400000: break
print('42B top400k: alpha tokens in 6B',len(present),'absent',len(absent),flush=True)
print('most frequent absent',[w for _,w in absent[:40]],flush=True)
A=random.sample(absent[:6000],50); P=random.sample([x for x in present if x[0]<absent[6000][0]],25)
def get(w):
    time.sleep(1.5)
    try:
        r=urllib.request.urlopen(urllib.request.Request(f'https://api.contexto.me/machado/en/game/1500/{w}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=25); return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,None
    except Exception as ex:
        time.sleep(15); return None,{'exc':repr(ex)[:60]}
res={'absent':[],'present':[]}
for k,S in (('absent',A),('present',P)):
    for n,w in S:
        st,b=get(w); res[k].append((n,w,st,b))
    ok=[x for x in res[k] if x[2]==200]; print(k,'non-answers',sum(x[2] is None for x in res[k]))
    print(k,'accepted',len(ok),'of',len(res[k]),[ (x[1],x[3]['lemma']) for x in ok][:30],flush=True)
json.dump(res,open(os.path.join(SP,'api','subset.json'),'w'),ensure_ascii=False,indent=0)
