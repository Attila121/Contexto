import json,collections,math
d=json.load(open('api/vocab_probe.json',encoding='utf-8'))
res=d['res']; bins=collections.defaultdict(list)
for x in res: bins[tuple(x['bin'])].append(x)
tot=0; print('stratified acceptance in GloVe 6B ^[a-z]+$ tokens (frequency-ordered):')
acc=[]
for b,v in sorted(bins.items()):
    c=collections.Counter()
    for x in v:
        if x['status']==200: c['ok']+=1; acc.append(x)
        else:
            e=(x['resp'] or {}).get('error','?'); c['common' if 'too common' in e else 'blocked' if "doesn't count" in e else 'unknown' if 'know' in e else e]+=1
    p=c['ok']/len(v); est=p*(b[1]-b[0]); tot+=est
    print(' ',b,dict(c),'accept',round(p,3),'est forms',round(est))
print('est accepted surface forms from 6B tokens ~',round(tot))
lem={}
for x in acc: lem[x['resp']['lemma']]=x['resp']['distance']
ds=sorted(lem.values())
print('accepted surface',len(acc),'distinct lemma',len(lem),'max dist',ds[-1],'top10',ds[-10:])
# distinct lemmas with same distance?
c=collections.Counter(lem.values()); print('distance collisions among distinct lemmas',[k for k,v in c.items() if v>1])
print('non-identity lemma examples',[(x['word'],x['resp']['lemma']) for x in acc if x['word']!=x['resp']['lemma']][:30])
m=d['multi']; vals=sorted(m.values()); print('multi-game max',vals[-1],'top10',vals[-10:],'n',len(vals))
k=len(ds); print('game-1500 german-tank N (uniform-assumption, lemma sample)',round(ds[-1]*(k+1)/k+1), 'k',k)
g=collections.defaultdict(list)
for key,v in m.items(): g[key.split('|')[0]].append(v)
print({a:max(b) for a,b in g.items()})
print('tip cap',d['tip_cap']); print('cons',[ (c['d'],c['tip'].get('lemma') if c['tip'] else None,c['game'].get('distance') if c['game'] else None,c['top_match']) for c in d['cons']])
