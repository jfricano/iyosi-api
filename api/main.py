import json
import logging
import math
import os
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from psycopg.errors import UniqueViolation

from .core import account, admin, auth_configured, check_rate, client_bucket, cursor_decode, cursor_encode, db, fail, hash_password, idempotent_lookup, idempotent_store, password_valid, point, sign, uid, utcnow, within_ncr
from .schemas import Ack, AddressSuggestions, ConfirmationIn, ConfirmationPage, DecisionAck, DecisionIn, Error, Kind, Login, Me, Place, PlacePage, PublicReview, Register, ReportIn, ReviewIn, ReviewPage, Status, SubmissionIn, SubmissionList, Token

app = FastAPI(title='iYosi API', version='1.0.0', description='Platform-neutral Metro Manila pilot API. Self-attested adult access is suitable only for a private pilot.', responses={400:{'model':Error},401:{'model':Error},403:{'model':Error},404:{'model':Error},409:{'model':Error},422:{'model':Error},429:{'model':Error},503:{'model':Error}})
operations_log = logging.getLogger('uvicorn.error')
ADMIN_DIR = Path(__file__).resolve().parent.parent / 'admin'
app.mount('/admin/assets', StaticFiles(directory=ADMIN_DIR / 'assets'), name='admin-assets')

@app.get('/admin', include_in_schema=False)
def admin_page():
    return FileResponse(ADMIN_DIR / 'index.html', headers={
        'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
    })

@app.middleware('http')
async def request_id(request: Request, call_next):
    rid = str(uuid4())
    request.state.request_id = rid
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers['X-Request-ID'] = rid
        return response
    finally:
        route = request.scope.get('route')
        operations_log.info(json.dumps({'event':'request_complete','request_id':rid,
            'method':request.method,'route':getattr(route,'path','unmatched'),
            'status':status,'duration_ms':round((time.perf_counter()-started)*1000,1)}))

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {'code':'http_error','message':str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={**detail,'request_id':request.state.request_id})

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    fields=[{'field':'.'.join(str(x) for x in error['loc']),'message':error['msg']} for error in exc.errors()]
    return JSONResponse(status_code=422,content={'code':'invalid_input','message':'Check the submitted fields','field_errors':fields,'request_id':request.state.request_id})

@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    rid=getattr(request.state,'request_id',str(uuid4()))
    operations_log.error('Unhandled API failure request_id=%s route=%s error_type=%s',rid,getattr(request.scope.get('route'),'path','unmatched'),type(exc).__name__)
    return JSONResponse(status_code=500,content={'code':'internal_error','message':'Request failed; try again later','request_id':rid},headers={'X-Request-ID':rid})

@app.get('/health')
def health():
    auth_configured()
    try:
        with db() as conn:
            configured=conn.execute('SELECT 1 FROM ncr_boundary WHERE id=1').fetchone()
    except psycopg.Error:
        fail(503,'database_unavailable','Database migrations are not ready')
    if not configured: fail(503,'boundary_unavailable','NCR boundary is not configured')
    return {'status':'ok'}

@app.post('/v1/auth/register', response_model=Token, status_code=201)
def register(data: Register, request: Request):
    auth_configured()
    email = data.email.strip().lower()
    if '@' not in email or '.' not in email.rsplit('@',1)[-1]:
        fail(422,'invalid_email','Enter a valid email address')
    # Count duplicate registration attempts too; an insert conflict rolls back its transaction.
    with db() as conn:
        check_rate(conn,client_bucket(request,'register'),5,3600)
    with db() as conn:
        account_id = uid('acct')
        try:
            conn.execute('INSERT INTO accounts(id,email,password_hash,adult_attested_at) VALUES (%s,%s,%s,now())',(account_id,email,hash_password(data.password)))
        except UniqueViolation:
            fail(409,'email_exists','Account already exists')
    return {'access_token':sign(account_id),'token_type':'bearer'}

@app.post('/v1/auth/token', response_model=Token)
def login(data: Login, request: Request):
    with db() as conn:
        check_rate(conn,client_bucket(request,'login'),10,900)
        row=conn.execute('SELECT id,password_hash FROM accounts WHERE email=%s AND disabled_at IS NULL',(data.email.strip().lower(),)).fetchone()
    if not row or not password_valid(data.password,row['password_hash']):
        fail(401,'invalid_credentials','Invalid email or password')
    return {'access_token':sign(row['id']),'token_type':'bearer'}

@app.get('/v1/me',response_model=Me)
def me(user=Depends(account)):
    return {'id':user['id'],'email':user['email'],'role':user['role'],'adult_attested_at':user['adult_attested_at']}

@app.post('/v1/me/deletion-requests', response_model=Ack, status_code=201)
def deletion_request(user=Depends(account)):
    with db() as conn:
        # Serialize requests for this account, including against a concurrent approval.
        if not conn.execute('SELECT id FROM accounts WHERE id=%s AND disabled_at IS NULL FOR UPDATE',(user['id'],)).fetchone():
            fail(401,'unauthenticated','Sign in to continue')
        row=conn.execute("SELECT id FROM deletion_requests WHERE account_id=%s AND state='pending'",(user['id'],)).fetchone()
        if row: return {'id':row['id'],'state':'pending'}
        item_id=uid('del')
        conn.execute('INSERT INTO deletion_requests(id,account_id) VALUES (%s,%s)',(item_id,user['id']))
        conn.execute('INSERT INTO moderation_cases(id,source_type,source_id,priority) VALUES (%s,%s,%s,1)',(uid('case'),'deletion_request',item_id))
    return {'id':item_id,'state':'pending'}

PLACE_SELECT="""p.id,p.name,p.kind,p.advisory_status,p.publication_state,ST_Y(p.location) AS lat,ST_X(p.location) AS lon,
 ST_Y(p.access_point) AS access_lat,ST_X(p.access_point) AS access_lon,p.address_label,p.access_notes,p.inside_venue,
 p.verification_reviewed_at,p.verification_public_source,p.updated_at,p.version,p.merged_into,
 (SELECT max(c.observed_at) FROM confirmations c WHERE c.place_id=p.id AND c.hidden_at IS NULL AND c.observation='still_there') AS last_confirmed_at,
 (SELECT count(*)::int FROM reviews r WHERE r.place_id=p.id AND r.hidden_at IS NULL AND r.deleted_at IS NULL) AS rating_count,
 (SELECT round(avg(r.stars)::numeric,1)::float FROM reviews r WHERE r.place_id=p.id AND r.hidden_at IS NULL AND r.deleted_at IS NULL) AS rating_average"""

def freshness(row):
    observed=row['last_confirmed_at']
    return 'fresh' if observed and observed>=utcnow()-timedelta(days=90) else 'stale'

def place_out(row):
    return {'id':row['id'],'name':row['name'],'kind':row['kind'],'advisory_status':row['advisory_status'],
        'location':{'lat':row['lat'],'lon':row['lon']},
        'access_point':{'lat':row['access_lat'],'lon':row['access_lon']} if row['access_lat'] is not None and row['publication_state']=='published' and row['advisory_status'] not in ('closed','prohibited') else None,
        'address_label':row['address_label'],'access_notes':row['access_notes'] if row['publication_state']=='published' and row['advisory_status'] not in ('closed','prohibited') else None,
        'inside_venue':row['inside_venue'],
        'verification':{'reviewed_at':row['verification_reviewed_at'],'public_source':row['verification_public_source']} if row['advisory_status']=='verified_designated' else None,
        'last_confirmed_at':row['last_confirmed_at'],'rating':{'average':row['rating_average'],'count':row['rating_count']},
        'updated_at':row['updated_at'],'version':row['version'],'merged_into':row['merged_into'],
        'directions_allowed':row['publication_state']=='published' and row['advisory_status'] not in ('closed','prohibited'),
        'freshness':freshness(row)}

def summary_out(row):
    return {'id':row['id'],'name':row['name'],'kind':row['kind'],'advisory_status':row['advisory_status'],
        'location':{'lat':row['lat'],'lon':row['lon']},
        'verification_reviewed_at':row['verification_reviewed_at'] if row['advisory_status']=='verified_designated' else None,
        'last_confirmed_at':row['last_confirmed_at'],'freshness':freshness(row),'rating':{'average':row['rating_average'],'count':row['rating_count']},
        'updated_at':row['updated_at'],
        'directions_allowed':row['publication_state']=='published' and row['advisory_status'] not in ('closed','prohibited')}

def bbox_parse(bbox):
    try:
        w,s,e,n=map(float,bbox.split(','))
    except (ValueError,AttributeError):
        fail(400,'invalid_bbox','bbox must be west,south,east,north')
    if not (-180<=w<e<=180 and -90<=s<n<=90 and e-w<=0.5 and n-s<=0.5):
        fail(400,'invalid_bbox','Viewport must be ordered and at most 0.5 degrees per side')
    return w,s,e,n

@app.get('/v1/places',response_model=PlacePage)
def places(bbox: str, kind: Kind | None=None, advisory_status: Status | None=None, cursor: str | None=None, limit: int=Query(50,ge=1,le=100), include_prohibited: bool=False):
    w,s,e,n=bbox_parse(bbox)
    after=cursor_decode(cursor)
    sql=f"SELECT {PLACE_SELECT} FROM places p WHERE p.publication_state='published' AND p.advisory_status<>'closed' AND ST_Intersects(p.location,ST_MakeEnvelope(%s,%s,%s,%s,4326)) AND p.id>%s"
    params=[w,s,e,n,after]
    if not include_prohibited and advisory_status!='prohibited': sql+=" AND p.advisory_status<>'prohibited'"
    if kind: sql+=' AND p.kind=%s'; params.append(kind)
    if advisory_status: sql+=' AND p.advisory_status=%s'; params.append(advisory_status)
    sql+=' ORDER BY p.id LIMIT %s'; params.append(limit+1)
    with db() as conn: rows=conn.execute(sql,params).fetchall()
    more=len(rows)>limit; rows=rows[:limit]
    return {'items':[summary_out(r) for r in rows],'next_cursor':cursor_encode(rows[-1]['id']) if more else None}

@app.get('/v1/places/nearby',response_model=PlacePage)
def nearby(request: Request, lat: float=Query(ge=-90,le=90), lon: float=Query(ge=-180,le=180), radius_m: int=Query(200,ge=50,le=1000), limit: int=Query(20,ge=1,le=50)):
    with db() as conn:
        check_rate(conn,client_bucket(request,'nearby'),60,3600)
        rows=conn.execute(f"SELECT {PLACE_SELECT} FROM places p WHERE p.publication_state='published' AND p.advisory_status NOT IN ('closed','prohibited') AND ST_DWithin(p.location::geography,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s) ORDER BY p.location <-> ST_SetSRID(ST_MakePoint(%s,%s),4326),p.id LIMIT %s",(lon,lat,radius_m,lon,lat,limit)).fetchall()
    return {'items':[summary_out(r) for r in rows],'next_cursor':None}

@app.get('/v1/places/{place_id}', response_model=Place)
def place_detail(place_id: str):
    with db() as conn:
        row=conn.execute(f'SELECT {PLACE_SELECT} FROM places p WHERE p.id=%s AND p.publication_state IN (\'published\',\'merged\')',(place_id,)).fetchone()
    if not row: fail(404,'not_found','Place unavailable')
    return place_out(row)

def visible_place(conn, place_id):
    row=conn.execute("SELECT id FROM places WHERE id=%s AND publication_state='published' AND advisory_status<>'closed'",(place_id,)).fetchone()
    if not row: fail(404,'not_found','Place unavailable')

@app.get('/v1/places/{place_id}/reviews',response_model=ReviewPage)
def reviews(place_id: str, cursor: str | None=None, limit: int=Query(20,ge=1,le=50)):
    after=cursor_decode(cursor)
    with db() as conn:
        visible_place(conn,place_id)
        rows=conn.execute("SELECT id,stars,body,created_at,updated_at FROM reviews WHERE place_id=%s AND hidden_at IS NULL AND deleted_at IS NULL AND id>%s ORDER BY id LIMIT %s",(place_id,after,limit+1)).fetchall()
    more=len(rows)>limit; rows=rows[:limit]
    return {'items':rows,'next_cursor':cursor_encode(rows[-1]['id']) if more else None}

@app.get('/v1/places/{place_id}/confirmations',response_model=ConfirmationPage)
def confirmations(place_id: str, cursor: str | None=None, limit: int=Query(20,ge=1,le=50)):
    after=cursor_decode(cursor)
    with db() as conn:
        visible_place(conn,place_id)
        rows=conn.execute("SELECT id,observation,observed_at,created_at FROM confirmations WHERE place_id=%s AND hidden_at IS NULL AND id>%s ORDER BY id LIMIT %s",(place_id,after,limit+1)).fetchall()
    more=len(rows)>limit; rows=rows[:limit]
    return {'items':rows,'next_cursor':cursor_encode(rows[-1]['id']) if more else None}

@app.get('/v1/address-suggestions',response_model=AddressSuggestions)
def suggestions(request: Request, q: str=Query(min_length=3,max_length=100)):
    api_key=os.environ.get('GEOAPIFY_API_KEY')
    provider='https://api.geoapify.com/v1/geocode/autocomplete' if api_key else os.environ.get('GEOCODER_URL')
    if not provider:
        operations_log.warning(json.dumps({'event':'geocoder_failure','reason':'not_configured','request_id':request.state.request_id}))
        fail(503,'geocoder_unavailable','Address search is not configured')
    with db() as conn: check_rate(conn,client_bucket(request,'search'),30,3600)
    try:
        params={'text':q,'limit':5,'format':'geojson','filter':'countrycode:ph','bias':'rect:120.90,14.35,121.20,14.85'} if api_key else {'q':q,'limit':5}
        response=httpx.get(provider,params=params,headers={'x-api-key':api_key} if api_key else None,timeout=3)
        response.raise_for_status()
        payload=response.json()
        features=payload['features']
        if not isinstance(features,list): raise ValueError('Invalid geocoder features')
        items=[]
        with db() as conn:
          for f in features[:5]:
            if f.get('geometry',{}).get('type')!='Point': continue
            lon,lat=f['geometry']['coordinates'][:2]
            if not isinstance(lon,(int,float)) or not isinstance(lat,(int,float)) or not math.isfinite(lon) or not math.isfinite(lat) or not (-180<=lon<=180 and -90<=lat<=90): continue
            properties=f.get('properties') or {}
            if not isinstance(properties,dict): continue
            label=str(properties.get('formatted') or properties.get('name') or properties.get('label') or q).strip()[:240]
            if label:
                if within_ncr(conn,lon,lat):
                    items.append({'label':label,'location':{'lat':lat,'lon':lon}})
        return {'items':items,'provider':'geoapify' if api_key else None}
    except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError,IndexError) as exc:
        operations_log.warning(json.dumps({'event':'geocoder_failure','reason':type(exc).__name__,
            'provider_status':exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None,
            'request_id':request.state.request_id}))
        fail(503,'geocoder_unavailable','Address search is temporarily unavailable')

@app.post('/v1/place-submissions',response_model=Ack,status_code=201)
def submit(data: SubmissionIn, request: Request, key: str | None=Header(default=None,alias='Idempotency-Key'), user=Depends(account)):
    route='place-submissions'
    with db() as conn:
        digest,prior=idempotent_lookup(conn,user['id'],route,key,data.model_dump(mode='json'))
        if prior: return prior
        check_rate(conn,'submission:'+user['id'],10,86400)
        if not within_ncr(conn,data.location.lon,data.location.lat): fail(422,'outside_ncr','Place pin must be inside NCR')
        if data.access_point and not within_ncr(conn,data.access_point.lon,data.access_point.lat): fail(422,'outside_ncr','Access point must be inside NCR')
        if data.intent=='correct': visible_place(conn,data.place_id)
        else:
            candidates=conn.execute("SELECT id FROM places WHERE publication_state='published' AND ST_DWithin(location::geography,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,50) LIMIT 5",(data.location.lon,data.location.lat)).fetchall()
            if candidates: fail(409,'likely_duplicate','Nearby places already exist: '+','.join(r['id'] for r in candidates))
        item_id=uid('sub'); case_id=uid('case')
        conn.execute("INSERT INTO place_submissions(id,account_id,intent,place_id,name,kind,location,access_point,address_label,access_notes,inside_venue,basis) VALUES (%s,%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),CASE WHEN %s::float IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END,%s,%s,%s,%s)",(item_id,user['id'],data.intent,data.place_id,data.name,data.kind,data.location.lon,data.location.lat,data.access_point.lon if data.access_point else None,data.access_point.lon if data.access_point else None,data.access_point.lat if data.access_point else None,data.address_label,data.access_notes,data.inside_venue,data.basis))
        conn.execute("INSERT INTO moderation_cases(id,source_type,source_id,priority) VALUES (%s,'submission',%s,0)",(case_id,item_id))
        result={'id':item_id,'state':'pending'}
        idempotent_store(conn,user['id'],route,key,digest,result)
    return result

@app.get('/v1/me/place-submissions',response_model=SubmissionList)
def my_submissions(user=Depends(account)):
    with db() as conn:
        rows=conn.execute('SELECT id,intent,place_id,name,kind,state,decision_reason,created_at,decided_at FROM place_submissions WHERE account_id=%s ORDER BY created_at DESC LIMIT 100',(user['id'],)).fetchall()
    return {'items':rows}

@app.post('/v1/places/{place_id}/confirmations',response_model=Ack,status_code=201)
def confirm(place_id: str, data: ConfirmationIn, key: str | None=Header(default=None,alias='Idempotency-Key'), user=Depends(account)):
    now=utcnow()
    if data.observed_at.tzinfo is None or data.observed_at>now+timedelta(minutes=5) or data.observed_at<now-timedelta(days=30): fail(422,'invalid_observed_at','Observation must be within the last 30 days')
    route='confirm:'+place_id
    with db() as conn:
        digest,prior=idempotent_lookup(conn,user['id'],route,key,data.model_dump(mode='json'))
        if prior: return prior
        visible_place(conn,place_id)
        recent=conn.execute("SELECT 1 FROM confirmations WHERE account_id=%s AND place_id=%s AND created_at>now()-interval '24 hours'",(user['id'],place_id)).fetchone()
        if recent: fail(429,'confirmation_frequency','Confirm this place at most once per day')
        item_id=uid('conf')
        conn.execute('INSERT INTO confirmations(id,place_id,account_id,observation,observed_at,access_note_suggestion) VALUES (%s,%s,%s,%s,%s,%s)',(item_id,place_id,user['id'],data.observation,data.observed_at,data.access_note_suggestion))
        if data.observation!='still_there' or data.access_note_suggestion:
            conn.execute("INSERT INTO moderation_cases(id,source_type,source_id,priority) VALUES (%s,'confirmation',%s,%s)",(uid('case'),item_id,2 if data.observation=='gone' else 1))
        result={'id':item_id,'state':'recorded'}
        idempotent_store(conn,user['id'],route,key,digest,result)
    return result

@app.put('/v1/places/{place_id}/reviews/me',response_model=PublicReview)
def put_review(place_id: str, data: ReviewIn, user=Depends(account)):
    with db() as conn:
        visible_place(conn,place_id)
        check_rate(conn,'review:'+user['id'],20,86400)
        item_id=uid('rev')
        row=conn.execute("INSERT INTO reviews(id,place_id,account_id,stars,body) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(place_id,account_id) DO UPDATE SET stars=EXCLUDED.stars,body=EXCLUDED.body,updated_at=CASE WHEN reviews.stars IS DISTINCT FROM EXCLUDED.stars OR reviews.body IS DISTINCT FROM EXCLUDED.body THEN now() ELSE reviews.updated_at END,deleted_at=NULL RETURNING id,stars,body,created_at,updated_at",(item_id,place_id,user['id'],data.stars,data.body)).fetchone()
    return row

@app.delete('/v1/places/{place_id}/reviews/me',status_code=204)
def delete_review(place_id: str,user=Depends(account)):
    with db() as conn:
        conn.execute('UPDATE reviews SET deleted_at=now() WHERE place_id=%s AND account_id=%s',(place_id,user['id']))

@app.post('/v1/reports',response_model=Ack,status_code=201)
def report(data: ReportIn,key: str | None=Header(default=None,alias='Idempotency-Key'),user=Depends(account)):
    route='reports'
    with db() as conn:
        digest,prior=idempotent_lookup(conn,user['id'],route,key,data.model_dump(mode='json'))
        if prior: return prior
        check_rate(conn,'report:'+user['id'],10,86400)
        if data.target_type=='place': visible_place(conn,data.target_id)
        else:
            found=conn.execute("SELECT 1 FROM reviews r JOIN places p ON p.id=r.place_id WHERE r.id=%s AND r.hidden_at IS NULL AND r.deleted_at IS NULL AND p.publication_state='published' AND p.advisory_status<>'closed'",(data.target_id,)).fetchone()
            if not found: fail(404,'not_found','Review unavailable')
        item_id=uid('rpt')
        conn.execute('INSERT INTO reports(id,account_id,target_type,target_id,reason,detail) VALUES (%s,%s,%s,%s,%s,%s)',(item_id,user['id'],data.target_type,data.target_id,data.reason,data.detail))
        conn.execute("INSERT INTO moderation_cases(id,source_type,source_id,priority) VALUES (%s,'report',%s,%s)",(uid('case'),item_id,2 if data.reason in ('closed','wrong_status','privacy') else 1))
        result={'id':item_id,'state':'received'}
        idempotent_store(conn,user['id'],route,key,digest,result)
    return result

@app.get('/v1/admin/moderation-cases')
def cases(state: str='open', cursor: str | None=None, limit: int=Query(30,ge=1,le=100), user=Depends(admin)):
    if state not in ('open','resolved'): fail(422,'invalid_state','Invalid case state')
    after=cursor_decode(cursor)
    with db() as conn:
        condition=''
        params=[state]
        if after:
            anchor=conn.execute('SELECT priority,created_at,id FROM moderation_cases WHERE id=%s',(after,)).fetchone()
            if not anchor: fail(400,'invalid_cursor','Invalid cursor')
            condition=' AND (priority < %s OR (priority = %s AND created_at > %s) OR (priority = %s AND created_at = %s AND id > %s))'
            params.extend([anchor['priority'],anchor['priority'],anchor['created_at'],anchor['priority'],anchor['created_at'],anchor['id']])
        params.append(limit+1)
        rows=conn.execute('SELECT id,source_type,source_id,state,priority,created_at,resolved_at FROM moderation_cases WHERE state=%s'+condition+' ORDER BY priority DESC,created_at,id LIMIT %s',params).fetchall()
    more=len(rows)>limit; rows=rows[:limit]
    return {'items':rows,'next_cursor':cursor_encode(rows[-1]['id']) if more else None}

@app.get('/v1/admin/moderation-cases/{case_id}')
def case_detail(case_id: str,user=Depends(admin)):
    with db() as conn:
        case=conn.execute('SELECT * FROM moderation_cases WHERE id=%s',(case_id,)).fetchone()
        if not case: fail(404,'not_found','Case unavailable')
        tables={'submission':'place_submissions','confirmation':'confirmations','report':'reports','deletion_request':'deletion_requests'}
        source=conn.execute(f'SELECT * FROM {tables[case["source_type"]]} WHERE id=%s',(case['source_id'],)).fetchone() if case['source_type'] in tables else conn.execute('SELECT * FROM places WHERE id=%s',(case['source_id'],)).fetchone()
        decisions=conn.execute('SELECT id,actor_id,action,target_type,target_id,reason,old_state,new_state,created_at FROM moderation_decisions WHERE case_id=%s ORDER BY created_at',(case_id,)).fetchall()
        coords=None
        if case['source_type']=='submission':
            coords=conn.execute('SELECT ST_Y(location) lat,ST_X(location) lon,ST_Y(access_point) access_lat,ST_X(access_point) access_lon FROM place_submissions WHERE id=%s',(case['source_id'],)).fetchone()
        elif case['source_type']=='manual':
            coords=conn.execute('SELECT ST_Y(location) lat,ST_X(location) lon FROM places WHERE id=%s',(case['source_id'],)).fetchone()
        place_id=None; review=None
        if source:
            if case['source_type']=='submission': place_id=source['place_id']
            elif case['source_type']=='confirmation': place_id=source['place_id']
            elif case['source_type']=='manual': place_id=source['id']
            elif case['source_type']=='report':
                if source['target_type']=='place': place_id=source['target_id']
                else:
                    review=conn.execute('SELECT id,place_id,stars,body,hidden_at,deleted_at,created_at,updated_at FROM reviews WHERE id=%s',(source['target_id'],)).fetchone()
                    if review: place_id=review['place_id']
        place=conn.execute('SELECT id,name,kind,advisory_status,publication_state,version,address_label,access_notes,inside_venue,verification_public_source,verification_evidence,ST_Y(location) lat,ST_X(location) lon FROM places WHERE id=%s',(place_id,)).fetchone() if place_id else None
    if source:
        source=dict(source)
        for field in ('location','access_point'):
            source[field]=None
        source.pop('password_hash',None)
        if coords:
            source['location']={'lat':coords['lat'],'lon':coords['lon']}
            source['access_point']={'lat':coords['access_lat'],'lon':coords['access_lon']} if coords.get('access_lat') is not None else None
    return {'case':case,'source':source,'context':{'place':place,'review':review},'decisions':decisions}

@app.post('/v1/admin/moderation-cases',response_model=Ack,status_code=201)
def manual_case(place_id: str,user=Depends(admin)):
    with db() as conn:
        if not conn.execute('SELECT 1 FROM places WHERE id=%s',(place_id,)).fetchone(): fail(404,'not_found','Place unavailable')
        item_id=uid('case')
        conn.execute("INSERT INTO moderation_cases(id,source_type,source_id,priority) VALUES (%s,'manual',%s,0)",(item_id,place_id))
    return {'id':item_id,'state':'open'}

def evidence_valid(data):
    if not data.evidence_type or not data.public_source or not data.evidence or not data.reviewed_at or data.reviewed_at.tzinfo is None or data.reviewed_at>utcnow():
        fail(422,'evidence_required','Verification needs evidence type, public source, private evidence, and reviewed_at')

def snapshot(row):
    return {k:v for k,v in row.items() if k != 'password_hash'}

@app.post('/v1/admin/moderation-cases/{case_id}/decisions',response_model=DecisionAck,status_code=201)
def decide(case_id: str,data: DecisionIn,user=Depends(admin)):
    with db() as conn:
        case=conn.execute('SELECT * FROM moderation_cases WHERE id=%s FOR UPDATE',(case_id,)).fetchone()
        if not case: fail(404,'not_found','Case unavailable')
        if case['state']!='open': fail(409,'case_resolved','Case already resolved')
        source_type=case['source_type']; source_id=case['source_id']
        target_type=''; target_id=''; old={}; new={}
        if source_type=='submission':
            sub=conn.execute('SELECT *,ST_X(location) lon,ST_Y(location) lat,ST_X(access_point) access_lon,ST_Y(access_point) access_lat FROM place_submissions WHERE id=%s FOR UPDATE',(source_id,)).fetchone()
            if sub['state']!='pending': fail(409,'submission_resolved','Submission already resolved')
            target_type='submission'; target_id=source_id; old=snapshot(sub)
            if data.action=='reject':
                conn.execute("UPDATE place_submissions SET state='rejected',decision_reason=%s,decided_at=now() WHERE id=%s",(data.reason,source_id))
            elif data.action=='merge':
                if sub['intent']!='create' or not data.canonical_place_id: fail(422,'invalid_merge','Merge needs a canonical place')
                visible_place(conn,data.canonical_place_id)
                conn.execute("UPDATE place_submissions SET state='merged',place_id=%s,decision_reason=%s,decided_at=now() WHERE id=%s",(data.canonical_place_id,data.reason,source_id))
            elif data.action=='publish':
                status=data.advisory_status or 'community_reported'
                if status=='verified_designated':
                    evidence_valid(data)
                    if sub['kind'] not in ('public_designated','venue_designated'): fail(422,'invalid_verification','Only designated kinds can be verified')
                if status=='closed': fail(422,'invalid_status','Do not publish a closed proposal')
                if sub['intent']=='create':
                    place_id=uid('plc')
                    conn.execute("INSERT INTO places(id,name,kind,advisory_status,location,access_point,address_label,access_notes,inside_venue,verification_reviewed_at,verification_public_source,verification_evidence) SELECT %s,name,kind,%s,location,access_point,address_label,access_notes,inside_venue,%s,%s,%s FROM place_submissions WHERE id=%s",(place_id,status,data.reviewed_at if status=='verified_designated' else None,data.public_source if status=='verified_designated' else None,(data.evidence_type+': '+data.evidence) if status=='verified_designated' else None,source_id))
                else:
                    place_id=sub['place_id']
                    row=conn.execute('SELECT version FROM places WHERE id=%s FOR UPDATE',(place_id,)).fetchone()
                    if data.expected_version is None or row['version']!=data.expected_version: fail(409,'version_conflict','Place version changed')
                    conn.execute("UPDATE places SET name=%s,kind=%s,location=%s,access_point=%s,address_label=%s,access_notes=%s,inside_venue=%s,advisory_status=%s,verification_reviewed_at=%s,verification_public_source=%s,verification_evidence=%s,version=version+1,updated_at=now() WHERE id=%s",(sub['name'],sub['kind'],sub['location'],sub['access_point'],sub['address_label'],sub['access_notes'],sub['inside_venue'],status,data.reviewed_at if status=='verified_designated' else None,data.public_source if status=='verified_designated' else None,(data.evidence_type+': '+data.evidence) if status=='verified_designated' else None,place_id))
                conn.execute("UPDATE place_submissions SET state='published',place_id=%s,decision_reason=%s,decided_at=now() WHERE id=%s",(place_id,data.reason,source_id))
            else: fail(422,'invalid_action','Action is not valid for a submission')
            new=snapshot(conn.execute('SELECT * FROM place_submissions WHERE id=%s',(source_id,)).fetchone())
            if data.action=='publish': new['published_place_id']=place_id
        else:
            if source_type=='confirmation':
                source=conn.execute('SELECT * FROM confirmations WHERE id=%s',(source_id,)).fetchone(); place_id=source['place_id']; review_id=None
                if data.action=='hide_confirmation':
                    target_type='confirmation'; target_id=source_id; old=snapshot(source)
                    conn.execute('UPDATE confirmations SET hidden_at=now() WHERE id=%s',(source_id,))
                    new=snapshot(conn.execute('SELECT * FROM confirmations WHERE id=%s',(source_id,)).fetchone())
                    place_id=None
            elif source_type=='report':
                source=conn.execute('SELECT * FROM reports WHERE id=%s',(source_id,)).fetchone()
                place_id=source['target_id'] if source['target_type']=='place' else None
                review_id=source['target_id'] if source['target_type']=='review' else None
            elif source_type=='manual': place_id=source_id; review_id=None
            elif source_type=='deletion_request':
                if data.action!='approve_deletion': fail(422,'invalid_action','Deletion request requires approve_deletion')
                request=conn.execute('SELECT * FROM deletion_requests WHERE id=%s FOR UPDATE',(source_id,)).fetchone()
                target_type='account'; target_id=request['account_id']
                old=snapshot(conn.execute('SELECT * FROM accounts WHERE id=%s',(target_id,)).fetchone()); old.pop('email',None)
                conn.execute("UPDATE accounts SET email=id || '@deleted.invalid',password_hash='deleted',disabled_at=now() WHERE id=%s",(target_id,))
                conn.execute("UPDATE deletion_requests SET state='completed' WHERE id=%s",(source_id,))
                new=snapshot(conn.execute('SELECT * FROM accounts WHERE id=%s',(target_id,)).fetchone())
                place_id=None; review_id=None
            else: fail(422,'invalid_case','Unsupported case source')
            if place_id:
                row=conn.execute('SELECT * FROM places WHERE id=%s FOR UPDATE',(place_id,)).fetchone()
                if not row: fail(404,'not_found','Place unavailable')
                if row['publication_state']=='merged' and data.action!='resolve':
                    fail(422,'invalid_action','Merged places cannot be changed or restored')
                target_type='place'; target_id=place_id; old=snapshot(row)
                if data.action!='resolve':
                    if data.expected_version is None or data.expected_version!=row['version']: fail(409,'version_conflict','Place version changed')
                if data.action=='verify_designated':
                    evidence_valid(data)
                    if row['kind'] not in ('public_designated','venue_designated'): fail(422,'invalid_verification','Only designated kinds can be verified')
                    conn.execute("UPDATE places SET advisory_status='verified_designated',verification_reviewed_at=%s,verification_public_source=%s,verification_evidence=%s,version=version+1,updated_at=now() WHERE id=%s",(data.reviewed_at,data.public_source,data.evidence_type+': '+data.evidence,place_id))
                elif data.action=='set_status':
                    if not data.advisory_status or data.advisory_status=='verified_designated': fail(422,'invalid_status','Use verify_designated for verification')
                    conn.execute("UPDATE places SET advisory_status=%s,verification_reviewed_at=NULL,verification_public_source=NULL,verification_evidence=NULL,version=version+1,updated_at=now() WHERE id=%s",(data.advisory_status,place_id))
                elif data.action=='merge_place':
                    if not data.canonical_place_id or data.canonical_place_id==place_id: fail(422,'invalid_merge','A different canonical place is required')
                    if row['publication_state']!='published': fail(422,'invalid_action','Only a published place can be merged')
                    visible_place(conn,data.canonical_place_id)
                    conn.execute("UPDATE places SET publication_state='merged',merged_into=%s,version=version+1,updated_at=now() WHERE id=%s",(data.canonical_place_id,place_id))
                elif data.action in ('hide_place','restore_place'):
                    required_state='published' if data.action=='hide_place' else 'hidden'
                    if row['publication_state']!=required_state: fail(422,'invalid_action','Place is not in the required publication state')
                    conn.execute('UPDATE places SET publication_state=%s,version=version+1,updated_at=now() WHERE id=%s',('hidden' if data.action=='hide_place' else 'published',place_id))
                elif data.action=='correct_place':
                    if data.location and not within_ncr(conn,data.location.lon,data.location.lat): fail(422,'outside_ncr','Pin must be inside NCR')
                    if data.access_point and not within_ncr(conn,data.access_point.lon,data.access_point.lat): fail(422,'outside_ncr','Access point must be inside NCR')
                    kind=data.kind or row['kind']
                    if kind=='venue_designated' and data.inside_venue is None and row['inside_venue'] is None: fail(422,'inside_venue_required','Venue designated areas must say inside or outside')
                    status='community_reported' if row['advisory_status']=='verified_designated' and kind not in ('public_designated','venue_designated') else row['advisory_status']
                    conn.execute("UPDATE places SET name=COALESCE(%s,name),kind=%s,location=COALESCE(%s,location),access_point=CASE WHEN %s THEN %s ELSE access_point END,access_notes=CASE WHEN %s THEN %s ELSE access_notes END,inside_venue=COALESCE(%s,inside_venue),advisory_status=%s,verification_reviewed_at=CASE WHEN %s='verified_designated' THEN verification_reviewed_at ELSE NULL END,verification_public_source=CASE WHEN %s='verified_designated' THEN verification_public_source ELSE NULL END,verification_evidence=CASE WHEN %s='verified_designated' THEN verification_evidence ELSE NULL END,version=version+1,updated_at=now() WHERE id=%s",(data.name,kind,point(data.location.lon,data.location.lat) if data.location else None,'access_point' in data.model_fields_set,point(data.access_point.lon,data.access_point.lat) if data.access_point else None,'access_notes' in data.model_fields_set,data.access_notes,data.inside_venue,status,status,status,status,place_id))
                elif data.action!='resolve': fail(422,'invalid_action','Action is not valid for this case')
                new=snapshot(conn.execute('SELECT * FROM places WHERE id=%s',(place_id,)).fetchone())
            elif review_id:
                row=conn.execute('SELECT * FROM reviews WHERE id=%s FOR UPDATE',(review_id,)).fetchone()
                if not row: fail(404,'not_found','Review unavailable')
                target_type='review'; target_id=review_id; old=snapshot(row)
                if data.action=='hide_review': conn.execute('UPDATE reviews SET hidden_at=now() WHERE id=%s',(review_id,))
                elif data.action=='restore_review': conn.execute('UPDATE reviews SET hidden_at=NULL WHERE id=%s',(review_id,))
                elif data.action!='resolve': fail(422,'invalid_action','Action is not valid for this review')
                new=snapshot(conn.execute('SELECT * FROM reviews WHERE id=%s',(review_id,)).fetchone())
        conn.execute("UPDATE moderation_cases SET state='resolved',resolved_at=now() WHERE id=%s",(case_id,))
        decision_id=uid('dec')
        conn.execute('INSERT INTO moderation_decisions(id,case_id,actor_id,action,target_type,target_id,reason,old_state,new_state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',(decision_id,case_id,user['id'],data.action,target_type,target_id,data.reason,json.dumps(old,default=str),json.dumps(new,default=str)))
    return {'id':decision_id,'case_id':case_id,'state':'resolved','target_type':target_type,'target_id':target_id}
