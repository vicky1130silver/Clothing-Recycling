from pathlib import Path
import csv,sqlite3,json,collections,datetime,decimal,hashlib
import numpy as np
REPO=Path(__file__).resolve().parents[2];ROOT=REPO/'02-data/raw';OUT=REPO/'02-data/summary';OUT.mkdir(parents=True,exist_ok=True)
db=ROOT/'analysis.sqlite'
if db.exists():db.unlink()
con=sqlite3.connect(db);con.row_factory=sqlite3.Row
con.execute('PRAGMA journal_mode=OFF');con.execute('PRAGMA synchronous=OFF')
con.execute('CREATE TABLE raw_events (row_id INTEGER PRIMARY KEY,event_time TEXT,event_type TEXT,product_id TEXT,category_id TEXT,category_code TEXT,brand TEXT,price_cents INTEGER,user_id TEXT,user_session TEXT)')
bad=0;batch=[]
with open(ROOT/'apparel_raw.csv',encoding='utf8',newline='') as f:
 for n,r in enumerate(csv.DictReader(f),1):
  try: price=int(decimal.Decimal(r['price'])*100)
  except:price=None;bad+=1
  batch.append((n,r['event_time'][:19],r['event_type'],r['product_id'],r['category_id'],r['category_code'],r['brand'] or None,price,r['user_id'] or None,r['user_session'] or None))
  if len(batch)>=10000:con.executemany('INSERT INTO raw_events VALUES (?,?,?,?,?,?,?,?,?,?)',batch);batch=[]
if batch:con.executemany('INSERT INTO raw_events VALUES (?,?,?,?,?,?,?,?,?,?)',batch)
SQL='''-- SQLite 3, all timestamps are UTC; range [2019-10-01,2019-10-15)
-- Step 1. Validate required behavior keys and remove exact duplicates on the nine source fields.
CREATE TABLE clean_events AS
WITH ranked AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY event_time,event_type,product_id,category_id,category_code,brand,price_cents,user_id,user_session ORDER BY row_id) AS dup_rank
 FROM raw_events
 WHERE user_id IS NOT NULL AND user_session IS NOT NULL AND product_id IS NOT NULL
 AND event_type IN ('view','cart','purchase') AND price_cents>=0
 AND event_time>='2019-10-01' AND event_time<'2019-10-15'
)
SELECT row_id,event_time,event_type,product_id,category_id,category_code,brand,price_cents,user_id,user_session
FROM ranked WHERE dup_rank=1;
CREATE INDEX ix_journey ON clean_events(user_id,user_session,product_id,event_type,event_time);
CREATE INDEX ix_user_time ON clean_events(user_id,event_time);
-- Step 2. Two-stage view-to-purchase funnel. This apparel subset has no cart events.
CREATE TABLE funnel_journeys AS
WITH v AS (SELECT user_id,user_session,product_id,MIN(event_time) AS view_time FROM clean_events WHERE event_type='view' GROUP BY 1,2,3),
c AS (SELECT v.*,MIN(e.event_time) AS cart_time FROM v LEFT JOIN clean_events e ON e.user_id=v.user_id AND e.user_session=v.user_session AND e.product_id=v.product_id AND e.event_type='cart' AND e.event_time>=v.view_time GROUP BY 1,2,3),
p AS (SELECT c.*,MIN(e.event_time) AS purchase_time FROM c LEFT JOIN clean_events e ON e.user_id=c.user_id AND e.user_session=c.user_session AND e.product_id=c.product_id AND e.event_type='purchase' AND e.event_time>=c.view_time GROUP BY 1,2,3)
SELECT * FROM p;
-- Step 3. First OBSERVED apparel activity cohort. No registration date is available.
CREATE TABLE activity_days AS SELECT DISTINCT user_id,DATE(event_time) AS active_day FROM clean_events;
CREATE INDEX ix_activity ON activity_days(user_id,active_day);
CREATE TABLE cohorts AS SELECT user_id,MIN(active_day) AS cohort_day FROM activity_days GROUP BY user_id;
CREATE TABLE retention AS
SELECT c.cohort_day,COUNT(*) AS cohort_users,
 CASE WHEN c.cohort_day<='2019-10-13' THEN SUM(EXISTS(SELECT 1 FROM activity_days a WHERE a.user_id=c.user_id AND a.active_day=DATE(c.cohort_day,'+1 day'))) END AS d1,
 CASE WHEN c.cohort_day<='2019-10-11' THEN SUM(EXISTS(SELECT 1 FROM activity_days a WHERE a.user_id=c.user_id AND a.active_day=DATE(c.cohort_day,'+3 day'))) END AS d3,
 CASE WHEN c.cohort_day<='2019-10-07' THEN SUM(EXISTS(SELECT 1 FROM activity_days a WHERE a.user_id=c.user_id AND a.active_day=DATE(c.cohort_day,'+7 day'))) END AS d7
FROM cohorts c GROUP BY c.cohort_day ORDER BY c.cohort_day;
-- Step 4. RFM on paid-event users, with inferred purchasing sessions, not actual order IDs.
CREATE TABLE rfm_base AS SELECT user_id,
 CAST(JULIANDAY('2019-10-15')-JULIANDAY(MAX(DATE(event_time))) AS INTEGER) AS recency_days,
 COUNT(DISTINCT user_session) AS purchase_sessions,
 SUM(price_cents)/100.0 AS purchase_event_value,
 COUNT(*) AS purchase_events
FROM clean_events WHERE event_type='purchase' AND price_cents>0 GROUP BY user_id;
'''
con.executescript(SQL)
def query(q):return [dict(r) for r in con.execute(q)]
def scalar(q):return con.execute(q).fetchone()[0]
stats={'raw_rows':n,'clean_rows':scalar('SELECT COUNT(*) FROM clean_events'),'users':scalar('SELECT COUNT(DISTINCT user_id) FROM clean_events'),'sessions':scalar("SELECT COUNT(*) FROM (SELECT DISTINCT user_id,user_session FROM clean_events)"),'products':scalar('SELECT COUNT(DISTINCT product_id) FROM clean_events'),'parse_invalid_price':bad,'events':query('SELECT event_type,COUNT(*) n FROM clean_events GROUP BY event_type'),'time_range':query('SELECT MIN(event_time) start,MAX(event_time) end FROM clean_events')[0]}
stats['duplicates']=scalar('SELECT COUNT(*) FROM raw_events')-scalar('SELECT COUNT(*) FROM (SELECT DISTINCT event_time,event_type,product_id,category_id,category_code,brand,price_cents,user_id,user_session FROM raw_events)')
stats['brand_missing']=scalar('SELECT COUNT(*) FROM clean_events WHERE brand IS NULL')
stats['zero_price']=scalar('SELECT COUNT(*) FROM clean_events WHERE price_cents=0')
stats['funnel']=query('SELECT COUNT(*) views,SUM(cart_time IS NOT NULL) carts,SUM(purchase_time IS NOT NULL) purchases FROM funnel_journeys')[0]
stats['daily']=query("SELECT DATE(event_time) day,COUNT(*) events,COUNT(DISTINCT user_id) users,SUM(event_type='purchase') purchases,SUM(CASE WHEN event_type='purchase' THEN price_cents ELSE 0 END)/100.0 purchase_value FROM clean_events GROUP BY 1 ORDER BY 1")
stats['retention']=query('SELECT * FROM retention')
stats['retention_aggregate']={}
for d in [1,3,7]:
 rs=[r for r in stats['retention'] if r['d'+str(d)] is not None];den=sum(x['cohort_users'] for x in rs);num=sum(x['d'+str(d)] for x in rs)
 stats['retention_aggregate'][str(d)]={'returned':num,'eligible':den,'rate':num/den}
buyers=query('SELECT * FROM rfm_base');ms=[r['purchase_event_value'] for r in buyers];qs=np.quantile(ms,[.25,.5,.75]).tolist()
for r in buyers:
 r['r_score']=4 if r['recency_days']<=3 else 3 if r['recency_days']<=7 else 2 if r['recency_days']<=10 else 1
 r['f_score']=min(r['purchase_sessions'],4)
 r['m_score']=1+sum(r['purchase_event_value']>q for q in qs)
 r['segment']='核心价值' if r['recency_days']<=7 and r['purchase_sessions']>=2 and r['purchase_event_value']>=qs[2] else '潜力复购' if r['recency_days']<=7 and r['purchase_sessions']>=2 else '近期首购' if r['recency_days']<=7 else '待唤回'
segments=[]
for name in ['核心价值','潜力复购','近期首购','待唤回']:
 rr=[r for r in buyers if r['segment']==name];segments.append({'segment':name,'buyers':len(rr),'value':round(sum(r['purchase_event_value'] for r in rr),2),'avg_value':round(np.mean([r['purchase_event_value'] for r in rr]),2) if rr else 0,'avg_f':round(np.mean([r['purchase_sessions'] for r in rr]),2) if rr else 0,'avg_r':round(np.mean([r['recency_days'] for r in rr]),2) if rr else 0})
stats['rfm']={'buyers':len(buyers),'m_quartiles':qs,'segments':segments,'total_value':round(sum(ms),2),'top20_share':sum(sorted(ms,reverse=True)[:int(np.ceil(len(ms)*.2))])/sum(ms),'repeat_buyers':sum(r['purchase_sessions']>=2 for r in buyers),'snapshot':'2019-10-15 UTC'}
stats['category']=query("SELECT category_code,COUNT(*) events,COUNT(DISTINCT user_id) users,SUM(event_type='purchase') purchase_events,SUM(CASE WHEN event_type='purchase' THEN price_cents ELSE 0 END)/100.0 value FROM clean_events GROUP BY 1 ORDER BY events DESC")
stats['category_funnel']=query('''SELECT e.category_code,COUNT(*) views,SUM(f.cart_time IS NOT NULL) carts,SUM(f.purchase_time IS NOT NULL) purchases FROM funnel_journeys f JOIN (SELECT user_id,user_session,product_id,MIN(category_code) category_code FROM clean_events GROUP BY 1,2,3) e ON e.user_id=f.user_id AND e.user_session=f.user_session AND e.product_id=f.product_id GROUP BY 1 ORDER BY views DESC''')
con.execute('CREATE TABLE rfm_users (user_id TEXT,recency_days INTEGER,purchase_sessions INTEGER,purchase_event_value REAL,purchase_events INTEGER,r_score INTEGER,f_score INTEGER,m_score INTEGER,segment TEXT)')
con.executemany('INSERT INTO rfm_users VALUES (:user_id,:recency_days,:purchase_sessions,:purchase_event_value,:purchase_events,:r_score,:f_score,:m_score,:segment)',buyers);con.commit()
for name,rs in [('daily',stats['daily']),('retention',stats['retention']),('rfm_segments',segments),('category',stats['category']),('category_funnel',stats['category_funnel'])]:
 with open(OUT/(name+'.csv'),'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
with open(OUT/'funnel.csv','w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['stage','journeys']);w.writerows([['浏览',stats['funnel']['views']],['浏览后购买',stats['funnel']['purchases']]])
(OUT/'analysis.sql').write_text(SQL,encoding='utf8');(ROOT/'results.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf8');(OUT/'results.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf8')
# Meaningful independent checks across the exported summary and SQL event controls.
assert stats['clean_rows']==sum(x['n'] for x in stats['events'])==sum(x['events'] for x in stats['daily'])
assert sum(s['buyers'] for s in segments)==len(buyers)
assert stats['funnel']['views']>=stats['funnel']['purchases']
assert abs(sum(s['value'] for s in segments)-stats['rfm']['total_value'])<.02
assert all(0<=v['rate']<=1 for v in stats['retention_aggregate'].values())
print(json.dumps({k:v for k,v in stats.items() if k not in ['category','daily','retention','category_funnel']},ensure_ascii=False,indent=2))
con.close()
