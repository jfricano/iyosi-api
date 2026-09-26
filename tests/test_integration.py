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
