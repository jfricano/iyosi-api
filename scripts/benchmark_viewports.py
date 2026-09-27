"""Benchmark actual viewport SQL against 5,000 synthetic NCR places in a marked test DB.

The fixture is inserted and rolled back in one transaction. This script never targets
the development or pilot database and never publishes its synthetic places.
"""
import json
import os
import statistics
import time

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from api.main import PLACE_SELECT
from scripts.ops_metrics import snapshot


def require_test_db(url):
    name=conninfo_to_dict(url).get('dbname','')
    if not name.endswith('_test'):
        raise SystemExit('TEST_DATABASE_URL must name a dedicated database ending in _test')


def insert_fixture(conn):
    if conn.execute("SELECT to_regclass('public.iyosi_integration_test_guard') AS marker").fetchone()['marker'] is None:
        raise SystemExit('Dedicated test database marker is missing')
    if not conn.execute("SELECT 1 FROM iyosi_integration_test_guard WHERE purpose='iyosi dedicated integration tests'").fetchone():
        raise SystemExit('Dedicated test database marker has the wrong purpose')
    if not conn.execute('SELECT 1 FROM ncr_boundary WHERE id=1').fetchone():
        raise SystemExit('Load the NCR boundary before benchmarking')
    if conn.execute("SELECT 1 FROM places WHERE id LIKE 'bench_%' LIMIT 1").fetchone():
        raise SystemExit('Unexpected benchmark rows already exist')

    rows=conn.execute("""WITH candidate AS (
        SELECT n, ST_SetSRID(ST_MakePoint(
            120.91 + ((n*73)%997)::float/997*0.27,
            14.41 + ((n*191)%991)::float/991*0.42),4326) AS geom
        FROM generate_series(1,40000) AS n
    ), inside AS (
        SELECT candidate.n,candidate.geom FROM candidate JOIN ncr_boundary b ON ST_Covers(b.geom,candidate.geom)
        ORDER BY n LIMIT 5000
    )
    INSERT INTO places(id,name,kind,advisory_status,publication_state,location)
    SELECT 'bench_' || lpad(n::text,8,'0'),'Synthetic benchmark ' || n,
        'informal_outdoor',
        CASE WHEN n%17=0 THEN 'closed' WHEN n%19=0 THEN 'prohibited' ELSE 'community_reported' END,
        CASE WHEN n%13=0 THEN 'hidden' ELSE 'published' END,geom
    FROM inside RETURNING id""").fetchall()
    if len(rows)!=5000:
        raise SystemExit(f'Expected 5,000 NCR points, got {len(rows)}')
    conn.execute("INSERT INTO accounts(id,email,password_hash,adult_attested_at) VALUES ('bench_actor','benchmark@example.invalid','unused',now())")
    conn.execute("""INSERT INTO reviews(id,place_id,account_id,stars,body)
        SELECT 'bench_rev_' || right(id,8),id,'bench_actor',1+(right(id,8)::int%5),'Synthetic review'
        FROM places WHERE id LIKE 'bench_%' AND right(id,8)::int%3=0""")
    conn.execute("""INSERT INTO confirmations(id,place_id,account_id,observation,observed_at)
        SELECT 'bench_conf_' || right(id,8),id,'bench_actor','still_there',
            now()-(right(id,8)::int%120 || ' days')::interval
        FROM places WHERE id LIKE 'bench_%' AND right(id,8)::int%2=0""")
    conn.execute("""INSERT INTO moderation_cases(id,source_type,source_id,state,priority,created_at)
        SELECT 'bench_case_' || right(id,8),'manual',id,'open',right(id,8)::int%3,
            now()-(right(id,8)::int%72 || ' hours')::interval
        FROM places WHERE id LIKE 'bench_%' AND right(id,8)::int%5=0""")
    for table in ('places','reviews','confirmations','moderation_cases'):
        conn.execute(f'ANALYZE {table}')
    return len(rows)


def nodes(plan):
    result=[]
    def visit(item):
        result.append({'node':item['Node Type'],'index':item.get('Index Name'),
                       'actual_rows':item.get('Actual Rows'),'rows_removed_by_filter':item.get('Rows Removed by Filter')})
        for child in item.get('Plans',[]):
            visit(child)
    visit(plan)
    return result


def measure(conn, name, box):
    sql=f"SELECT {PLACE_SELECT} FROM places p WHERE p.publication_state='published' AND p.advisory_status<>'closed' AND ST_Intersects(p.location,ST_MakeEnvelope(%s,%s,%s,%s,4326)) AND p.id>%s AND p.advisory_status<>'prohibited' ORDER BY p.id LIMIT %s"
    params=(*box,'',51)
    for _ in range(10):
        conn.execute(sql,params).fetchall()
    samples=[]
    for _ in range(100):
        started=time.perf_counter()
        results=conn.execute(sql,params).fetchall()
        samples.append((time.perf_counter()-started)*1000)
    explain=conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql,params).fetchone()['QUERY PLAN'][0]
    return {'viewport':name,'bbox':box,'page_rows':len(results),
            'query_p50_ms':round(statistics.median(samples),2),
            'query_p95_ms':round(sorted(samples)[94],2),
            'explain_execution_ms':round(explain['Execution Time'],2),
            'plan_nodes':nodes(explain['Plan'])}


def main():
    url=os.environ.get('TEST_DATABASE_URL')
    if not url:
        raise SystemExit('Set TEST_DATABASE_URL to a marked, migrated PostGIS test database')
    require_test_db(url)
    conn=psycopg.connect(url,row_factory=dict_row)
    try:
        count=insert_fixture(conn)
        report={'synthetic_places':count,
                'small':measure(conn,'small',(120.99,14.59,121.04,14.64)),
                'large':measure(conn,'large',(120.94,14.50,121.10,14.70)),
                'operations':snapshot(conn)}
        print(json.dumps(report,indent=2))
    finally:
        conn.rollback()
        conn.close()


if __name__=='__main__':
    main()
