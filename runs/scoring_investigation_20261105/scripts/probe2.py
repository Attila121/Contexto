import json,time,urllib.request,urllib.parse,sys
B='https://api.contexto.me/machado/en'
UA={'User-Agent':'Mozilla/5.0 (research-readonly)'}
def get(path):
    time.sleep(0.7)
    req=urllib.request.Request(B+path,headers=UA)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            hdr={k.lower():v for k,v in r.headers.items()}
            return r.status,hdr,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        hdr={k.lower():v for k,v in e.headers.items()}
        try: body=json.loads(e.read().decode())
        except Exception: body=None
        return e.code,hdr,body
G=1500
groups={
 'case_space':['PEAR','Pear',' pear','pear ','pe ar','pear.','pear-','pear1'],
 'inflection':['running','ran','runs','runner','better','best','good','well','mice','mouse','geese','goose','went','go','going','was','been','children','child','leaves','leaf','leave','saw','see','seen','glasses','glass','data','datum','news','bigger','big','happily','happy','happiness','pears','peaches','apples','candied','candy'],
 'stop_common':['the','of','and','a','an','to','in','is','it','you','that','he','she','they','we','i','this','there','some','very','not','with','for','on','at'],
 'proper_entities':['london','paris','obama','google','microsoft','brazil','john','mary','einstein','tokyo'],
 'nonword_foreign':['asdfqwer','qwertyuiop','zzzz','caf\u00e9','cafe','na\u00efve','naive','pa\u00eds','fruta','manzana','2022','1999','covid','chatgpt','iphone','bitcoin','selfie','wifi','email','e-mail','t-shirt'],
 'synonym_pairs':['tv','television','car','automobile','doctor','physician','usa','america'],
 'rare':['aardwolf','zymurgy','quixotic','defenestrate','sesquipedalian','floccinaucinihilipilification','antidisestablishmentarianism','xylophone','abaci','obsequious','perspicacious','grandiloquent','nudiustertian','borborygmus','ultracrepidarian'],
}
out={}
for g,ws in groups.items():
    for w in ws:
        st,h,b=get(f'/game/{G}/'+urllib.parse.quote(w,safe=''))
        out[f'{g}|{w}']=(st,b)
        print(g,repr(w),st,json.dumps(b,ensure_ascii=False),flush=True)
json.dump(out,open(sys.argv[1],'w'),ensure_ascii=False,indent=0)
