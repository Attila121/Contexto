import json,time,urllib.request,sys
def get(w,g=1500):
    time.sleep(0.8)
    try:
        r=urllib.request.urlopen(urllib.request.Request(f'https://api.contexto.me/machado/en/game/{g}/{w}',headers={'User-Agent':'Mozilla/5.0 (research-readonly)'}),timeout=25); return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except Exception: return {'status':e.code}
for w in ['colour','color','coloured','colored','vapour','vapor','neighbour','neighbor','neighbourhood','neighborhood','centre','center','theatre','theater','grey','gray','launcher','launching','launch','donut','doughnut','tv','television','airplane','aeroplane','data','datum','capita','caput','stamina','stamen','better','well','worse','bad']:
    print(w,get(w),flush=True)
