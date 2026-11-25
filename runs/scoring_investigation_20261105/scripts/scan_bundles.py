import os,re,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
d=sys.argv[1]
kw=re.compile(r'glove|nilc|word2vec|fasttext|wang2vec|embedding|numberbatch|stanford|usp\b|cosine|cosseno|lemma',re.I)
for f in sorted(os.listdir(d)):
    s=open(os.path.join(d,f),encoding='utf-8',errors='replace').read()
    hits={}
    for m in kw.finditer(s):
        hits.setdefault(m.group().lower(),[]).append(m.start())
    api=re.findall(r'https?://[a-z.]*contexto\.me[^"`\']*',s)
    print(f,len(s),{k:len(v) for k,v in hits.items()},sorted(set(api))[:4])
    for k in ('glove','nilc'):
        if k in hits:
            i=hits[k][0]; print('   >>',k,':',s[max(0,i-300):i+300].replace('\n',' '))
