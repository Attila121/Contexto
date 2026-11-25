# Small number of queries to WordPolo public demo rank endpoint, paired with Contexto game 0 (banana). Read-only.
import json,time,urllib.request,sys
UA={'User-Agent':'Mozilla/5.0 (research-readonly)','Content-Type':'application/json','Accept':'application/json'}
def rank(target,guess):
    time.sleep(1.0)
    req=urllib.request.Request('https://wordpolo-demo.vercel.app/api/rank',data=json.dumps({'target_word':target,'guess':guess}).encode(),headers=UA,method='POST')
    try:
        r=urllib.request.urlopen(req,timeout=25); return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        b=e.read().decode('utf-8','replace')
        try: return e.code,json.loads(b)
        except Exception: return e.code,b[:200]
    except Exception as ex: return None,repr(ex)[:200]
def ctx(game,w):
    time.sleep(0.7)
    req=urllib.request.Request(f'https://api.contexto.me/machado/en/game/{game}/{w}',headers={'User-Agent':UA['User-Agent']})
    try:
        r=urllib.request.urlopen(req,timeout=25); return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,None
words=['pineapple','strawberry','fruit','apple','coconut','mango','peanut','chocolate','bananas','apples','the','obama','google','john','tokyo','bitcoin','iphone','asdfqwer','zzzz','1999','plantation','car','city','computer','music','river','mountain','philosophy','justice','government','democracy','hospital','television','tv','running','ran','datum','physician','quixotic','perspicacious','ecuador','chiquita','yellow','monkey','peel','republic','tree','bread']
out=[]
for w in words:
    a=rank('banana',w); c=ctx(0,w)
    out.append({'word':w,'wordpolo':a,'contexto':c}); print(w,'| WP',a,'| CTX',c,flush=True)
json.dump(out,open(sys.argv[1],'w'),ensure_ascii=False,indent=0)
