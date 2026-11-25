import os,re,sys,json
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
d=sys.argv[1]
rows=[]
for f in sorted(os.listdir(d)):
    s=open(os.path.join(d,f),encoding='utf-8',errors='replace').read()
    has_i18n=bool(re.search(r'how[Tt]oPlay|Como jogar|Find the secret word|Encontre a palavra',s))
    en=bool(re.search(r'Find the secret word',s))
    st='nlp.stanford.edu/projects/glove' in s
    nilc='nilc.icmc.usp.br' in s or 'NILC' in s
    gl=re.search(r'glove',s,re.I) is not None
    faq='How is the word order defined' in s
    p=re.search(r'The data used to calculate the proximity[^"`]{0,80}',s)
    faqtxt=re.search(r'How is the word order defined\?.{0,20}a1:[`"](.{0,260})',s)
    rows.append((f[:8],f[9:],len(s),has_i18n,en,gl,st,nilc,faq,bool(p)))
    print(f[:8],f[9:][:26].ljust(26),str(len(s)).rjust(8),'i18n' if has_i18n else '----','EN' if en else '--','GLOVE' if gl else '-----','STANF' if st else '-----','NILC' if nilc else '----','FAQ' if faq else '---')
