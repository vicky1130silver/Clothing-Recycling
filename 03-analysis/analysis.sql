-- SQLite 3, all timestamps are UTC; range [2019-10-01,2019-10-15)
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
