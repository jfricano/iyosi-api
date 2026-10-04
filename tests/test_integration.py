"""Run against a dedicated migrated PostGIS database via TEST_DATABASE_URL."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import psycopg
from psycopg.conninfo import conninfo_to_dict
from fastapi.testclient import TestClient

os.environ.setdefault('IYOSI_SECRET','test-secret-0123456789-0123456789')
from api import core
from api.main import app

TEST_DB=os.environ.get('TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not TEST_DB,reason='TEST_DATABASE_URL is not set')

@pytest.fixture(scope='module')
def setup_db():
    database_name=conninfo_to_dict(TEST_DB).get('dbname','')
    if not database_name.endswith('_test'):
        raise RuntimeError('TEST_DATABASE_URL must name a dedicated database ending in _test')
    core.DATABASE_URL=TEST_DB
    with psycopg.connect(TEST_DB) as conn:
        guard=conn.execute("SELECT to_regclass('public.iyosi_integration_test_guard')").fetchone()[0]
        if not guard or not conn.execute("SELECT 1 FROM iyosi_integration_test_guard WHERE purpose='iyosi dedicated integration tests'").fetchone():
            raise RuntimeError('Dedicated test database marker is missing; refusing to truncate tables')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for path in sorted(Path('migrations').glob('*.sql')):
            if conn.execute('SELECT 1 FROM schema_migrations WHERE version=%s',(path.name,)).fetchone():
                continue
            # Older test databases applied 001 without recording its version.
            if path.name != '001_initial.sql' or not conn.execute("SELECT to_regclass('public.accounts')").fetchone()[0]:
                conn.execute(path.read_text())
            conn.execute('INSERT INTO schema_migrations(version) VALUES (%s)',(path.name,))
        conn.execute('TRUNCATE moderation_decisions,moderation_cases,idempotency_records,reports,deletion_requests,reviews,confirmations,place_submissions,places,accounts,rate_buckets CASCADE')
        conn.execute("INSERT INTO ncr_boundary(id,geom,source) VALUES (1,ST_Multi(ST_MakeEnvelope(120.8,14.3,121.2,14.9,4326)),'test fixture') ON CONFLICT(id) DO UPDATE SET geom=EXCLUDED.geom,source=EXCLUDED.source")
    yield

@pytest.fixture
def client(setup_db):
    return TestClient(app)

def register(client,email):
    response=client.post('/v1/auth/register',json={'email':email,'password':'long valid password','adult_attested':True})
    assert response.status_code==201,response.text
    return {'Authorization':'Bearer '+response.json()['access_token']}

def test_full_moderation_and_signal_separation(client):
    import secrets
    marker=secrets.token_hex(4)
    contributor=register(client,f'person-{marker}@example.com')
    administrator=register(client,f'admin-{marker}@example.com')
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("UPDATE accounts SET role='admin' WHERE email=%s",(f'admin-{marker}@example.com',))
    payload={'intent':'create','name':'Fixture area '+marker,'kind':'venue_designated','inside_venue':False,'location':{'lat':14.60,'lon':121.00},'access_point':{'lat':14.6001,'lon':121.0001},'basis':'Visited and saw a sign'}
    submission=client.post('/v1/place-submissions',json=payload,headers={**contributor,'Idempotency-Key':'submission-'+marker})
    assert submission.status_code==201,submission.text
    assert client.post('/v1/place-submissions',json=payload,headers={**contributor,'Idempotency-Key':'submission-'+marker}).json()==submission.json()
    assert client.get('/v1/places',params={'bbox':'120.9,14.5,121.1,14.7'}).json()['items']==[]
    cases=client.get('/v1/admin/moderation-cases',headers=administrator).json()['items']
    case=next(x for x in cases if x['source_id']==submission.json()['id'])
    forbidden=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=contributor,json={'action':'publish','reason':'Should be forbidden'})
    assert forbidden.status_code==403
    decision=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=administrator,json={'action':'publish','reason':'Evidence pending; publish as reported'})
    assert decision.status_code==201,decision.text
    place_id=decision.json()['target_id']
    # Submission decision target is submission; place ID is in the private audit snapshot.
    detail=client.get(f"/v1/admin/moderation-cases/{case['id']}",headers=administrator).json()
    place_id=detail['decisions'][0]['new_state']['published_place_id']
    own_submissions=client.get('/v1/me/place-submissions',headers=contributor).json()['items']
    assert next(item for item in own_submissions if item['id']==submission.json()['id'])['place_id']==place_id
    assert client.get(f'/v1/places/{place_id}').json()['advisory_status']=='community_reported'
    confirmation=client.post(f'/v1/places/{place_id}/confirmations',headers={**contributor,'Idempotency-Key':'confirmation-'+marker},json={'observation':'still_there','observed_at':datetime.now(timezone.utc).isoformat()})
    assert confirmation.status_code==201,confirmation.text
    review=client.put(f'/v1/places/{place_id}/reviews/me',headers=contributor,json={'stars':5,'body':'Clear access'})
    assert review.status_code==200,review.text
    before=client.get(f'/v1/places/{place_id}').json()
    assert before['advisory_status']=='community_reported'
    assert before['last_confirmed_at'] is not None
    assert before['rating']=={'average':5.0,'count':1}
    manual=client.post('/v1/admin/moderation-cases',params={'place_id':place_id},headers=administrator).json()['id']
    denied=client.post(f'/v1/admin/moderation-cases/{manual}/decisions',headers=administrator,json={'action':'verify_designated','reason':'Reviewed evidence','expected_version':1})
    assert denied.status_code==422
    verified=client.post(f'/v1/admin/moderation-cases/{manual}/decisions',headers=administrator,json={'action':'verify_designated','reason':'Reviewed signage on site','expected_version':1,'evidence_type':'signage','evidence':'Photo of current posted sign','public_source':'Posted venue sign','reviewed_at':datetime.now(timezone.utc).isoformat()})
    assert verified.status_code==201,verified.text
    after=client.get(f'/v1/places/{place_id}').json()
    assert after['advisory_status']=='verified_designated'
    assert after['verification']['public_source']=='Posted venue sign'
    assert after['rating']==before['rating']
    assert 'account_id' not in after
    assert 'verification_evidence' not in after


def test_create_submission_merge_keeps_canonical_place_link(client):
    import secrets
    marker=secrets.token_hex(4)
    contributor=register(client,f'merge-person-{marker}@example.com')
    administrator=register(client,f'merge-admin-{marker}@example.com')
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("UPDATE accounts SET role='admin' WHERE email=%s",(f'merge-admin-{marker}@example.com',))

    def propose(name, lat):
        payload={'intent':'create','name':name,'kind':'informal_outdoor',
                 'location':{'lat':lat,'lon':121.0},'basis':'Observed during test setup'}
        response=client.post('/v1/place-submissions',json=payload,
                             headers={**contributor,'Idempotency-Key':f'{name}-{marker}'})
        assert response.status_code==201,response.text
        submission_id=response.json()['id']
        cases=client.get('/v1/admin/moderation-cases',headers=administrator).json()['items']
        return submission_id,next(item['id'] for item in cases if item['source_id']==submission_id)

    canonical_submission,canonical_case=propose('Canonical fixture',14.7)
    published=client.post(f'/v1/admin/moderation-cases/{canonical_case}/decisions',
                          headers=administrator,json={'action':'publish','reason':'Reviewed test fixture'})
    assert published.status_code==201,published.text
    own=client.get('/v1/me/place-submissions',headers=contributor).json()['items']
    canonical_id=next(item for item in own if item['id']==canonical_submission)['place_id']

    duplicate_submission,duplicate_case=propose('Duplicate fixture',14.8)
    merged=client.post(f'/v1/admin/moderation-cases/{duplicate_case}/decisions',
                       headers=administrator,json={'action':'merge','reason':'Merged test proposal',
                                                   'canonical_place_id':canonical_id})
    assert merged.status_code==201,merged.text
    own=client.get('/v1/me/place-submissions',headers=contributor).json()['items']
    duplicate=next(item for item in own if item['id']==duplicate_submission)
    assert duplicate['state']=='merged'
    assert duplicate['place_id']==canonical_id
    assert client.get('/v1/places',params={'bbox':'120.9,14.75,121.1,14.85'}).json()['items']==[]


def fixture_account(role='contributor'):
    """Avoid the public registration rate limit in broad integration matrices."""
    import secrets
    account_id='acct_'+secrets.token_hex(12)
    email=f'{account_id}@example.com'
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("INSERT INTO accounts(id,email,password_hash,adult_attested_at,role) VALUES (%s,%s,'test-only',now(),%s)",
                     (account_id,email,role))
    return account_id, {'Authorization':'Bearer '+core.sign(account_id)}


def fixture_place(*, lat=14.6, lon=121.0, kind='public_designated', status='community_reported'):
    import secrets
    place_id='plc_'+secrets.token_hex(12)
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("""INSERT INTO places(id,name,kind,advisory_status,location,access_point,access_notes)
                     VALUES (%s,'Test pin',%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),
                     ST_SetSRID(ST_MakePoint(%s,%s),4326),'Old entrance')""",
                     (place_id,kind,status,lon,lat,lon+.0001,lat+.0001))
    return place_id


def fixture_case(place_id):
    import secrets
    case_id='case_'+secrets.token_hex(12)
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("INSERT INTO moderation_cases(id,source_type,source_id) VALUES (%s,'manual',%s)",(case_id,place_id))
    return case_id


def decide_place(client, admin_headers, place_id, action, version, **extra):
    case_id=fixture_case(place_id)
    response=client.post(f'/v1/admin/moderation-cases/{case_id}/decisions',headers=admin_headers,
                         json={'action':action,'reason':'Reviewed test evidence','expected_version':version,**extra})
    return case_id,response


def test_spatial_status_and_correction_integrity(client):
    _,admin_headers=fixture_account('admin')
    place_id=fixture_place()
    bbox='120.9,14.5,121.1,14.7'
    assert [x['id'] for x in client.get('/v1/places',params={'bbox':bbox}).json()['items'] if x['id']==place_id]==[place_id]
    assert client.get('/v1/places',params={'bbox':'120.7,14.5,120.8,14.7'}).json()['items']==[]
    assert place_id in [x['id'] for x in client.get('/v1/places/nearby',params={'lat':14.6,'lon':121.0,'radius_m':50}).json()['items']]
    assert place_id not in [x['id'] for x in client.get('/v1/places/nearby',params={'lat':14.7,'lon':121.0,'radius_m':50}).json()['items']]
    _,outside=decide_place(client,admin_headers,place_id,'correct_place',1,location={'lat':14.1,'lon':121.0})
    assert outside.status_code==422 and outside.json()['code']=='outside_ncr'
    _,correction=decide_place(client,admin_headers,place_id,'correct_place',1,
                              location={'lat':14.62,'lon':121.02},access_point=None,access_notes=None)
    assert correction.status_code==201,correction.text
    detail=client.get(f'/v1/places/{place_id}').json()
    assert detail['location']=={'lat':14.62,'lon':121.02}
    assert detail['access_point'] is None and detail['access_notes'] is None
    _,stale=decide_place(client,admin_headers,place_id,'set_status',1,advisory_status='prohibited')
    assert stale.status_code==409 and stale.json()['code']=='version_conflict'
    _,prohibited=decide_place(client,admin_headers,place_id,'set_status',2,advisory_status='prohibited')
    assert prohibited.status_code==201,prohibited.text
    assert place_id not in [x['id'] for x in client.get('/v1/places',params={'bbox':bbox}).json()['items']]
    assert place_id in [x['id'] for x in client.get('/v1/places',params={'bbox':bbox,'include_prohibited':True}).json()['items']]
    assert client.get(f'/v1/places/{place_id}').json()['directions_allowed'] is False
    _,closed=decide_place(client,admin_headers,place_id,'set_status',3,advisory_status='closed')
    assert closed.status_code==201,closed.text
    assert client.get(f'/v1/places/{place_id}').json()['advisory_status']=='closed'
    assert client.get(f'/v1/places/{place_id}').json()['access_point'] is None
    _,hidden=decide_place(client,admin_headers,place_id,'hide_place',4)
    assert hidden.status_code==201,hidden.text
    assert client.get(f'/v1/places/{place_id}').status_code==404


def test_confirmations_reviews_reports_and_privacy(client):
    _,contributor=fixture_account()
    _,second_contributor=fixture_account()
    _,admin_headers=fixture_account('admin')
    place_id=fixture_place(lat=14.64)
    now=datetime.now(timezone.utc).isoformat()
    changed=client.post(f'/v1/places/{place_id}/confirmations',headers={**contributor,'Idempotency-Key':'changed-observation'},
                        json={'observation':'changed','observed_at':now,'access_note_suggestion':'Entrance moved'})
    assert changed.status_code==201,changed.text
    assert client.post(f'/v1/places/{place_id}/confirmations',headers={**contributor,'Idempotency-Key':'changed-observation'},
                       json={'observation':'changed','observed_at':now,'access_note_suggestion':'Entrance moved'}).json()==changed.json()
    conflict=client.post(f'/v1/places/{place_id}/confirmations',headers={**contributor,'Idempotency-Key':'changed-observation'},
                         json={'observation':'gone','observed_at':now})
    assert conflict.status_code==409 and conflict.json()['code']=='idempotency_conflict'
    gone=client.post(f'/v1/places/{place_id}/confirmations',headers={**contributor,'Idempotency-Key':'gone-observation'},
                     json={'observation':'gone','observed_at':now})
    assert gone.status_code==429 and gone.json()['code']=='confirmation_frequency'
    gone=client.post(f'/v1/places/{place_id}/confirmations',headers={**second_contributor,'Idempotency-Key':'gone-observation'},
                     json={'observation':'gone','observed_at':now})
    assert gone.status_code==201,gone.text
    detail=client.get(f'/v1/places/{place_id}').json()
    assert detail['last_confirmed_at'] is None and detail['advisory_status']=='community_reported'
    public=client.get(f'/v1/places/{place_id}/confirmations').json()['items']
    assert len(public)==2
    assert all('account_id' not in observation and 'access_note_suggestion' not in observation for observation in public)
    cases=client.get('/v1/admin/moderation-cases',headers=admin_headers).json()['items']
    case=next(x for x in cases if x['source_id']==changed.json()['id'])
    gone_case=next(x for x in cases if x['source_id']==gone.json()['id'])
    resolved=client.post(f"/v1/admin/moderation-cases/{gone_case['id']}/decisions",headers=admin_headers,
                         json={'action':'resolve','reason':'Reviewed and kept current status'})
    assert resolved.status_code==201,resolved.text
    repeated=client.post(f"/v1/admin/moderation-cases/{gone_case['id']}/decisions",headers=admin_headers,
                         json={'action':'resolve','reason':'Reviewed and kept current status'})
    assert repeated.status_code==409 and repeated.json()['code']=='case_resolved'
    assert client.get(f'/v1/places/{place_id}').json()['advisory_status']=='community_reported'
    hidden=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=admin_headers,
                       json={'action':'hide_confirmation','reason':'Suggestion contains private information'})
    assert hidden.status_code==201,hidden.text
    remaining=client.get(f'/v1/places/{place_id}/confirmations').json()['items']
    assert len(remaining)==1 and remaining[0]['id']==gone.json()['id']
    review=client.put(f'/v1/places/{place_id}/reviews/me',headers=contributor,json={'stars':4,'body':'Useful details'})
    assert review.status_code==200,review.text
    report=client.post('/v1/reports',headers={**contributor,'Idempotency-Key':'review-report-one'},
                       json={'target_type':'review','target_id':review.json()['id'],'reason':'privacy','detail':'Personal detail'})
    assert report.status_code==201,report.text
    assert client.post('/v1/reports',headers={**contributor,'Idempotency-Key':'review-report-one'},
                       json={'target_type':'review','target_id':review.json()['id'],'reason':'privacy','detail':'Personal detail'}).json()==report.json()
    cases=client.get('/v1/admin/moderation-cases',headers=admin_headers).json()['items']
    case=next(x for x in cases if x['source_id']==report.json()['id'])
    hidden=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=admin_headers,
                       json={'action':'hide_review','reason':'Privacy report was valid'})
    assert hidden.status_code==201,hidden.text
    assert client.get(f'/v1/places/{place_id}').json()['rating']=={'average':None,'count':0}
    assert client.get(f'/v1/places/{place_id}/reviews').json()['items']==[]
    assert client.get('/v1/admin/moderation-cases',headers=contributor).status_code==403
    with psycopg.connect(TEST_DB) as conn:
        decisions=conn.execute('SELECT count(*) FROM moderation_decisions WHERE case_id=%s',(gone_case['id'],)).fetchone()[0]
        assert decisions==1
        with pytest.raises(psycopg.Error):
            conn.execute('SAVEPOINT immutable_decision')
            conn.execute('DELETE FROM moderation_decisions WHERE case_id=%s',(gone_case['id'],))
        conn.rollback()


def test_merge_restore_and_deletion_guards(client):
    account_id,contributor=fixture_account()
    _,admin_headers=fixture_account('admin')
    canonical=fixture_place(lat=14.66)
    duplicate=fixture_place(lat=14.67)
    _,merged=decide_place(client,admin_headers,duplicate,'merge_place',1,canonical_place_id=canonical)
    assert merged.status_code==201,merged.text
    merged_detail=client.get(f'/v1/places/{duplicate}').json()
    assert merged_detail['merged_into']==canonical
    assert merged_detail['directions_allowed'] is False
    assert merged_detail['access_point'] is None and merged_detail['access_notes'] is None
    _,restore=decide_place(client,admin_headers,duplicate,'restore_place',2)
    assert restore.status_code==422 and restore.json()['code']=='invalid_action'
    review=client.put(f'/v1/places/{canonical}/reviews/me',headers=contributor,
                      json={'stars':3,'body':'This review should disappear with its place'})
    assert review.status_code==200,review.text
    _,hide_canonical=decide_place(client,admin_headers,canonical,'hide_place',1)
    assert hide_canonical.status_code==201,hide_canonical.text
    report_hidden=client.post('/v1/reports',headers={**contributor,'Idempotency-Key':'hidden-review-report'},
                              json={'target_type':'review','target_id':review.json()['id'],'reason':'privacy'})
    assert report_hidden.status_code==404
    _,restored_canonical=decide_place(client,admin_headers,canonical,'restore_place',2)
    assert restored_canonical.status_code==201,restored_canonical.text
    deletion=client.post('/v1/me/deletion-requests',headers=contributor)
    assert deletion.status_code==201,deletion.text
    assert client.post('/v1/me/deletion-requests',headers=contributor).json()==deletion.json()
    cases=client.get('/v1/admin/moderation-cases',headers=admin_headers).json()['items']
    case=next(x for x in cases if x['source_id']==deletion.json()['id'])
    denied=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=admin_headers,
                       json={'action':'resolve','reason':'Must approve deletion'})
    assert denied.status_code==422
    approved=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=admin_headers,
                         json={'action':'approve_deletion','reason':'User requested deletion'})
    assert approved.status_code==201,approved.text
    assert client.get('/v1/me',headers=contributor).status_code==401
    with psycopg.connect(TEST_DB) as conn:
        row=conn.execute('SELECT email,disabled_at FROM accounts WHERE id=%s',(account_id,)).fetchone()
        assert row[0].endswith('@deleted.invalid') and row[1] is not None
        decision=conn.execute('SELECT old_state,new_state FROM moderation_decisions WHERE case_id=%s',(case['id'],)).fetchone()
        assert decision is not None
        assert 'email' not in decision[0]
        assert decision[1]['email'].endswith('@deleted.invalid')


def test_auth_tokens_login_and_disabled_accounts(client):
    import base64
    import hashlib
    import hmac
    import json
    import time
    account_id,headers=fixture_account()
    with psycopg.connect(TEST_DB) as conn:
        conn.execute('UPDATE accounts SET password_hash=%s WHERE id=%s',
                     (core.hash_password('correct long password'),account_id))
    assert client.get('/v1/me',headers=headers).status_code==200
    assert client.get('/v1/me',headers={'Authorization':headers['Authorization']+'x'}).status_code==401
    payload=base64.urlsafe_b64encode(json.dumps({'sub':account_id,'exp':int(time.time())-1}).encode()).decode().rstrip('=')
    mac=hmac.new(core.SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()
    assert client.get('/v1/me',headers={'Authorization':f'Bearer {payload}.{mac}'}).status_code==401
    email=f'{account_id}@example.com'
    login=client.post('/v1/auth/token',json={'email':email,'password':'correct long password'})
    assert login.status_code==200,login.text
    with psycopg.connect(TEST_DB) as conn:
        conn.execute('UPDATE accounts SET disabled_at=now() WHERE id=%s',(account_id,))
    assert client.get('/v1/me',headers=headers).status_code==401
    assert client.get('/v1/me',headers={'Authorization':'Bearer '+login.json()['access_token']}).status_code==401
    assert client.post('/v1/auth/token',json={'email':email,'password':'correct long password'}).status_code==401


def test_rate_limit_concurrency_and_expiry(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    import secrets
    bucket='concurrent-'+secrets.token_hex(6)
    barrier=Barrier(12)

    def attempt(_):
        barrier.wait()
        try:
            with core.db() as conn:
                core.check_rate(conn,bucket,5,3600)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes=list(pool.map(attempt,range(12)))
    assert outcomes.count(200)==5 and outcomes.count(429)==7
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute('SELECT count FROM rate_buckets WHERE bucket=%s',(bucket,)).fetchone()[0]==5
        conn.execute("UPDATE rate_buckets SET expires_at=now()-interval '1 second' WHERE bucket=%s",(bucket,))
    with core.db() as conn:
        core.check_rate(conn,bucket,5,3600)
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute('SELECT count FROM rate_buckets WHERE bucket=%s',(bucket,)).fetchone()[0]==1


def test_submission_idempotency_concurrency_and_expiry(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import secrets
    _,headers=fixture_account()
    marker=secrets.token_hex(5)
    request_headers={**headers,'Idempotency-Key':'concurrent-'+marker}
    payload={'intent':'create','name':'Concurrent '+marker,'kind':'informal_outdoor',
             'location':{'lat':14.71,'lon':121.01},'basis':'Observed during a concurrency test'}
    barrier=Barrier(2)

    def send(_):
        barrier.wait()
        return client.post('/v1/place-submissions',headers=request_headers,json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(send,range(2)))
    assert [response.status_code for response in responses]==[201,201]
    assert responses[0].json()==responses[1].json()
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute('SELECT count(*) FROM place_submissions WHERE name=%s',(payload['name'],)).fetchone()[0]==1
        conn.execute("UPDATE idempotency_records SET created_at=now()-interval '25 hours' WHERE key=%s",(request_headers['Idempotency-Key'],))
    expired=client.post('/v1/place-submissions',headers=request_headers,json=payload)
    assert expired.status_code==201,expired.text
    assert expired.json()['id']!=responses[0].json()['id']
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute('SELECT count(*) FROM place_submissions WHERE name=%s',(payload['name'],)).fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM idempotency_records WHERE key=%s',(request_headers['Idempotency-Key'],)).fetchone()[0]==1


def test_concurrent_deletion_requests_create_one_case(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    account_id,headers=fixture_account()
    barrier=Barrier(2)

    def send(_):
        barrier.wait()
        return client.post('/v1/me/deletion-requests',headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(send,range(2)))
    assert [response.status_code for response in responses]==[201,201]
    assert responses[0].json()==responses[1].json()
    with psycopg.connect(TEST_DB) as conn:
        requests=conn.execute("SELECT id FROM deletion_requests WHERE account_id=%s AND state='pending'",(account_id,)).fetchall()
        assert len(requests)==1
        assert conn.execute("SELECT count(*) FROM moderation_cases WHERE source_type='deletion_request' AND source_id=%s",(requests[0][0],)).fetchone()[0]==1


def test_operator_recovery_and_ephemeral_metadata_cleanup(client):
    import secrets
    import subprocess
    import sys
    account_id,headers=fixture_account()
    email=f'{account_id}@example.com'
    env={**os.environ,'DATABASE_URL':TEST_DB}
    grant=subprocess.run([sys.executable,'scripts/grant_admin.py',email],env=env,capture_output=True,text=True)
    assert grant.returncode==0,grant.stderr
    assert client.get('/v1/me',headers=headers).json()['role']=='admin'
    token=secrets.token_hex(5)
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("""INSERT INTO idempotency_records(account_id,route,key,request_hash,response_status,response_body,created_at)
                     VALUES (%s,'test',%s,'digest',201,'{}',now()-interval '25 hours'),
                            (%s,'test',%s,'digest',201,'{}',now())""",
                     (account_id,'expired-'+token,account_id,'current-'+token))
        conn.execute("INSERT INTO rate_buckets(bucket,count,expires_at) VALUES (%s,1,now()-interval '1 second'),(%s,1,now()+interval '1 hour')",
                     ('expired-'+token,'current-'+token))
    cleanup=subprocess.run([sys.executable,'scripts/cleanup.py'],env=env,capture_output=True,text=True)
    assert cleanup.returncode==0,cleanup.stderr
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute('SELECT key FROM idempotency_records WHERE route=%s',('test',)).fetchall()==[('current-'+token,)]
        assert conn.execute('SELECT bucket FROM rate_buckets WHERE bucket IN (%s,%s)',('expired-'+token,'current-'+token)).fetchall()==[('current-'+token,)]
        conn.execute('UPDATE accounts SET disabled_at=now() WHERE id=%s',(account_id,))
    denied=subprocess.run([sys.executable,'scripts/grant_admin.py',email],env=env,capture_output=True,text=True)
    assert denied.returncode!=0 and 'No active account' in denied.stderr


def test_duplicate_registration_attempts_count_against_limit(client):
    import secrets
    marker=secrets.token_hex(5)
    email=f'duplicate-{marker}@example.com'
    payload={'email':email,'password':'long valid password','adult_attested':True}
    with psycopg.connect(TEST_DB) as conn:
        conn.execute('DELETE FROM rate_buckets')
    assert client.post('/v1/auth/register',json=payload).status_code==201
    for _ in range(4):
        response=client.post('/v1/auth/register',json=payload)
        assert response.status_code==409 and response.json()['code']=='email_exists'
    limited=client.post('/v1/auth/register',json=payload)
    assert limited.status_code==429 and limited.json()['code']=='rate_limited'


def test_own_review_newest_first_pages_and_observation_tolerance(client):
    from datetime import timedelta
    _,author=fixture_account()
    _,admin_headers=fixture_account('admin')
    place_id=fixture_place(lat=14.68)
    assert client.get(f'/v1/places/{place_id}/reviews/me',headers=author).status_code==404
    assert client.get(f'/v1/places/{place_id}/reviews/me').status_code==401
    written=client.put(f'/v1/places/{place_id}/reviews/me',headers=author,json={'stars':5,'body':'Clear signage'})
    assert written.status_code==200,written.text
    assert client.get(f'/v1/places/{place_id}/reviews/me',headers=author).json()==written.json()
    with psycopg.connect(TEST_DB) as conn:
        conn.execute('UPDATE reviews SET hidden_at=now() WHERE id=%s',(written.json()['id'],))
    assert client.get(f'/v1/places/{place_id}/reviews/me',headers=author).json()['id']==written.json()['id']
    assert client.delete(f'/v1/places/{place_id}/reviews/me',headers=author).status_code==204
    assert client.get(f'/v1/places/{place_id}/reviews/me',headers=author).status_code==404

    now=datetime.now(timezone.utc)
    ages=[3,1,5,2,4]
    with psycopg.connect(TEST_DB) as conn:
        for age in ages:
            account_id,_=fixture_account()
            conn.execute("INSERT INTO reviews(id,place_id,account_id,stars,created_at,updated_at) VALUES (%s,%s,%s,4,%s,%s)",
                         (f'rev_age{age}_{place_id}',place_id,account_id,now-timedelta(days=age),now-timedelta(days=age)))
            conn.execute("INSERT INTO confirmations(id,place_id,account_id,observation,observed_at) VALUES (%s,%s,%s,'still_there',%s)",
                         (f'conf_age{age}_{place_id}',place_id,account_id,now-timedelta(days=age)))
    for resource in ('reviews','confirmations'):
        seen=[]; cursor=None
        while True:
            page=client.get(f'/v1/places/{place_id}/{resource}',params={'limit':2,**({'cursor':cursor} if cursor else {})})
            assert page.status_code==200,page.text
            seen+=[item['id'] for item in page.json()['items']]
            cursor=page.json()['next_cursor']
            if not cursor: break
        assert [int(x.split('_')[1][3:]) for x in seen]==sorted(ages),resource
    assert client.get(f'/v1/places/{place_id}/reviews',params={'cursor':'cGxjX2FiYw'}).json()['code']=='invalid_cursor'

    _,observer=fixture_account()
    edge=(now-timedelta(days=30,minutes=2)).isoformat()
    accepted=client.post(f'/v1/places/{place_id}/confirmations',headers={**observer,'Idempotency-Key':'edge-'+place_id},
                         json={'observation':'still_there','observed_at':edge})
    assert accepted.status_code==201,accepted.text
    _,late=fixture_account()
    too_old=client.post(f'/v1/places/{place_id}/confirmations',headers={**late,'Idempotency-Key':'old-'+place_id},
                        json={'observation':'still_there','observed_at':(now-timedelta(days=31)).isoformat()})
    assert too_old.status_code==422 and too_old.json()['code']=='invalid_observed_at'
    naive=client.post(f'/v1/places/{place_id}/confirmations',headers={**late,'Idempotency-Key':'naive-'+place_id},
                      json={'observation':'still_there','observed_at':now.replace(tzinfo=None).isoformat()})
    assert naive.status_code==422 and 'time zone' in naive.json()['message']


def test_correction_cannot_publish_onto_merged_place(client):
    _,contributor=fixture_account()
    _,admin_headers=fixture_account('admin')
    duplicate=fixture_place(lat=14.69)
    canonical=fixture_place(lat=14.695)
    correction=client.post('/v1/place-submissions',headers={**contributor,'Idempotency-Key':'late-correction-'+duplicate},
                           json={'intent':'correct','place_id':duplicate,'name':'Renamed pin','kind':'informal_outdoor',
                                 'location':{'lat':14.69,'lon':121.0},'basis':'Sign was renamed on site'})
    assert correction.status_code==201,correction.text
    _,merged=decide_place(client,admin_headers,duplicate,'merge_place',1,canonical_place_id=canonical)
    assert merged.status_code==201,merged.text
    cases=client.get('/v1/admin/moderation-cases',params={'limit':100},headers=admin_headers).json()['items']
    case=next(x for x in cases if x['source_id']==correction.json()['id'])
    published=client.post(f"/v1/admin/moderation-cases/{case['id']}/decisions",headers=admin_headers,
                          json={'action':'publish','reason':'Correction looked right','expected_version':2})
    assert published.status_code==422 and published.json()['code']=='invalid_action'
    assert client.get(f'/v1/places/{duplicate}').json()['name']=='Test pin'


def test_token_response_reports_expiry(client):
    import secrets
    from datetime import timedelta
    with psycopg.connect(TEST_DB) as conn:
        conn.execute('DELETE FROM rate_buckets')
    response=client.post('/v1/auth/register',json={'email':f'expiry-{secrets.token_hex(4)}@example.com','password':'long valid password','adult_attested':True})
    assert response.status_code==201,response.text
    expires=datetime.fromisoformat(response.json()['expires_at'].replace('Z','+00:00'))
    assert timedelta(hours=23,minutes=59)<expires-datetime.now(timezone.utc)<=timedelta(hours=24)
    assert client.post('/v1/auth/token',json={'email':'x@example.com','password':'p'*129}).status_code==422
