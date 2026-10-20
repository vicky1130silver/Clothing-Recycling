import urllib.request,gzip,io,csv,json,time,hashlib
from pathlib import Path
URL='https://data.rees46.com/datasets/marketplace/2019-Oct.csv.gz'
dest=Path(__file__).resolve().parents[2]/'02-data/raw';dest.mkdir(parents=True,exist_ok=True)
start=time.time();scanned=0;kept=0;last='';categories={}
req=urllib.request.Request(URL,headers={'User-Agent':'PortfolioResearch/1.0'})
with urllib.request.urlopen(req,timeout=120) as resp:
 print('HTTP',resp.status,'length',resp.headers.get('Content-Length'),flush=True)
 with gzip.GzipFile(fileobj=resp) as gz,io.TextIOWrapper(gz,encoding='utf-8',newline='') as txt,open(dest/'apparel_raw.csv','w',encoding='utf-8',newline='') as out:
  reader=csv.reader(txt);header=next(reader);w=csv.writer(out);w.writerow(header)
  for row in reader:
   scanned+=1;last=row[0]
   if row[0]>='2019-10-15':break
   if row[4].startswith('apparel.'):
    w.writerow(row);kept+=1;categories[row[4]]=categories.get(row[4],0)+1
   if scanned%1000000==0: print('scanned',scanned,'kept',kept,'at',last,'seconds',round(time.time()-start),flush=True)
p=dest/'apparel_raw.csv'
manifest={'source_url':URL,'publisher':'REES46','description_url':'https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store','scope':'category_code starts apparel.; 2019-10-01 <= event_time < 2019-10-15 UTC','scanned_until_boundary':scanned,'boundary_event':last,'raw_selected_rows':kept,'selected_file_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'categories':categories,'seconds':round(time.time()-start,1),'note':'Streamed official gzip until first event at Oct15; omitted later events. File contains unchanged selected source rows, not synthetic or own-app logs.'}
(dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False),flush=True)
