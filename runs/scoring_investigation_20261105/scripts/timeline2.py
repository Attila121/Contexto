import os,re,sys,gzip,brotli,json
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
d=sys.argv[1]; prev=None; rows=[]
for f in sorted(os.listdir(d)):
    b=open(os.path.join(d,f),'rb').read(); enc='raw'
    if b[:2]==b'\x1f\x8b':
        try: b=gzip.decompress(b); enc='gz'
        except Exception as e: enc='gz-trunc'
    elif not re.match(rb'\s*(\(|!|/|var|"use|function|\{)',b[:40]):
        try: b=brotli.decompress(b); enc='br'
        except Exception as e: enc='br-fail'
    s=b.decode('utf-8','replace')
    ok=len(s)>200000
    gl=bool(re.search(r'glove',s,re.I)); st='nlp.stanford.edu/projects/glove' in s; nilc=bool(re.search(r'nilc',s,re.I))
    en='Find the secret word' in s or 'secret word' in s
    fq='How is the word order defined' in s
    fa=re.search(r'How is the word order defined\?[`"\']?,\s*a1:\s*[`"\'](.{0,180})',s)
    ip=re.search(r'infoModal:\{.{0,420}?p3:[`"\']([^`"\']{0,120})[`"\'],\s*sourceName:[`"\']([^`"\']{0,60})[`"\'],\s*sourceLink:[`"\']([^`"\']{0,100})',s)
    t=(gl,st,nilc,fq, ip.group(2) if ip else None, ip.group(3) if ip else None, fa.group(1)[:70] if fa else None)
    rows.append(dict(date=f[:8],file=f[9:],enc=enc,len=len(s),glove=gl,stanford=st,nilc=nilc,faq=fq,src=ip.group(2) if ip else None,link=ip.group(3) if ip else None,faq_start=fa.group(1) if fa else None))
    open(os.path.join(os.path.dirname(d),'dec_'+f),'w',encoding='utf-8').write(s) if False else None
    mark='*' if t!=prev else ' '
    print(mark,f[:8],f[14:32].ljust(18),enc.ljust(8),str(len(s)).rjust(8),'GL' if gl else '--','ST' if st else '--','NI' if nilc else '--','FQ' if fq else '--',t[4],t[6])
    prev=t
json.dump(rows,open(sys.argv[2],'w'),indent=0)
