import gzip,re,sys,glob,os
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
d=sys.argv[1]
def load(pat):
    f=sorted(glob.glob(os.path.join(d,pat)))[0]; b=open(f,'rb').read()
    if b[:2]==b'\x1f\x8b': b=gzip.decompress(b)
    return f,b.decode('utf-8','replace')
for pat in ['20260228*','20260311*']:
    f,s=load(pat); print('=====',os.path.basename(f),len(s))
    for m in re.finditer(r'sourceName|sourceLink|nlp\.stanford|nilc\.icmc|SBWCE|sbwce|dccuchile|crscardellino|fasttext|glove',s,re.I):
        pass
    for m in list(re.finditer(r'sourceLink',s))[:8]:
        print(' src>',s[max(0,m.start()-210):m.start()+120].replace('\n',' '))
    # usage in component
    for m in list(re.finditer(r'infoModal\.(p3|sourceName|sourceLink)',s))[:6]:
        print(' use>',s[max(0,m.start()-200):m.start()+200].replace('\n',' '))
    for m in list(re.finditer(r'infoModal:\{',s))[:6]:
        print(' info>',s[m.start():m.start()+520].replace('\n',' '))
f,s=load('20230301*')
print('===== 2023-03 EN usage'); 
for m in list(re.finditer(r'infoModal\.p3',s))[:2]:
    print(s[max(0,m.start()-300):m.start()+500])
