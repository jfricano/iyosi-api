import os
os.environ.setdefault('IYOSI_SECRET','test-secret-0123456789-0123456789')

from fastapi.testclient import TestClient
from pydantic import ValidationError
from api.main import app, bbox_parse
from api.schemas import SubmissionIn, ConfirmationIn
from api.core import cursor_encode,cursor_decode,hash_password,password_valid,sign


def test_openapi_contract_has_platform_neutral_resources():
    schema=app.openapi()
    paths=schema['paths']
    for path in ('/v1/places','/v1/place-submissions','/v1/places/{place_id}/confirmations','/v1/places/{place_id}/reviews/me','/v1/reports','/v1/admin/moderation-cases/{case_id}/decisions'):
        assert path in paths
    submission=schema['components']['schemas']['SubmissionIn']['properties']
    assert 'advisory_status' not in submission
    assert 'verification' not in submission
    assert 'location' in submission
    assert 'access_point' in submission


def test_strict_submission_rejects_user_verification_and_invalid_intent():
    valid={'intent':'create','name':'Test area','kind':'informal_outdoor','location':{'lat':14.6,'lon':121.0},'basis':'Observed on site'}
    try:
        SubmissionIn.model_validate({**valid,'advisory_status':'verified_designated'})
    except ValidationError: pass
    else: assert False
    try:
        SubmissionIn.model_validate({**valid,'intent':'correct'})
    except ValidationError: pass
    else: assert False


def test_viewport_and_cursor_bounds():
    assert bbox_parse('120.9,14.5,121.1,14.8')==(120.9,14.5,121.1,14.8)
    for bad in ('120.9,14.5,121.5,14.8','121,14,120,15','bad'):
        try: bbox_parse(bad)
        except Exception: pass
        else: assert False
    assert cursor_decode(cursor_encode('plc_abc'))=='plc_abc'


def test_password_hash_is_salted():
    one=hash_password('a long valid password')
    two=hash_password('a long valid password')
    assert one!=two
    assert password_valid('a long valid password',one)
    assert not password_valid('wrong',one)


def test_openapi_can_be_served_without_database():
    response=TestClient(app).get('/openapi.json')
    assert response.status_code==200
    assert response.json()['info']['title']=='iYosi API'

def test_place_output_keeps_signals_separate():
    from datetime import datetime, timezone
    from api.main import place_out, summary_out
    now=datetime.now(timezone.utc)
    row={'id':'plc_example','name':'Example','kind':'venue_designated','advisory_status':'community_reported','publication_state':'published','lat':14.6,'lon':121.0,'access_lat':14.6001,'access_lon':121.0001,'address_label':None,'access_notes':'Public entrance','inside_venue':False,'verification_reviewed_at':now,'verification_public_source':'Old evidence','updated_at':now,'version':1,'merged_into':None,'last_confirmed_at':now,'rating_count':2,'rating_average':4.5}
    result=place_out(row)
    assert result['verification'] is None
    assert result['last_confirmed_at']==now
    assert result['freshness']=='fresh'
    assert result['directions_allowed']
    assert result['rating']=={'average':4.5,'count':2}
    assert 'access_notes' not in summary_out(row)
    row['advisory_status']='prohibited'
    assert place_out(row)['access_point'] is None
    assert place_out(row)['access_notes'] is None
    assert not place_out(row)['directions_allowed']


def test_checked_in_openapi_matches_runtime():
    import json
    from pathlib import Path
    assert json.loads(Path('docs/openapi.json').read_text())==app.openapi()

def test_adult_gate_validation_and_error_shape():
    client=TestClient(app)
    response=client.post('/v1/auth/register',json={'email':'person@example.com','password':'long valid password','adult_attested':False})
    assert response.status_code==422
    payload=response.json()
    assert payload['code']=='invalid_input'
    assert payload['request_id']==response.headers['X-Request-ID']
    assert any(item['field']=='body.adult_attested' for item in payload['field_errors'])

def test_public_response_models_validate_signal_fields():
    from datetime import datetime, timezone
    from api.main import place_out, summary_out
    from api.schemas import Place, PlaceSummary
    now=datetime.now(timezone.utc)
    row={'id':'plc_example','name':'Example','kind':'venue_designated','advisory_status':'verified_designated','publication_state':'published','lat':14.6,'lon':121.0,'access_lat':None,'access_lon':None,'address_label':None,'access_notes':None,'inside_venue':False,'verification_reviewed_at':now,'verification_public_source':'Posted sign','updated_at':now,'version':2,'merged_into':None,'last_confirmed_at':None,'rating_count':0,'rating_average':None}
    assert Place.model_validate(place_out(row)).verification.public_source=='Posted sign'
    assert PlaceSummary.model_validate(summary_out(row)).directions_allowed


def test_unexpected_error_is_correlated_without_exposing_exception(monkeypatch,caplog):
    from contextlib import contextmanager
    from api import main

    @contextmanager
    def broken_db():
        raise RuntimeError('private database connection details')
        yield

    monkeypatch.setattr(main,'db',broken_db)
    response=TestClient(app,raise_server_exceptions=False).get('/v1/places',params={'bbox':'120.9,14.5,121.1,14.7'})
    assert response.status_code==500
    assert response.json()['code']=='internal_error'
    assert response.json()['request_id']==response.headers['X-Request-ID']
    assert 'private database connection details' not in response.text
    assert 'private database connection details' not in caplog.text
    assert response.json()['request_id'] in caplog.text


def test_invalid_signing_secret_disables_auth_and_health(monkeypatch):
    from api import core
    monkeypatch.setattr(core,'SECRET','')
    client=TestClient(app)
    assert client.get('/health').json()['code']=='auth_unavailable'
    assert client.get('/v1/me',headers={'Authorization':'Bearer forged.token'}).json()['code']=='auth_unavailable'
    register=client.post('/v1/auth/register',json={'email':'secret-config@example.com',
        'password':'long valid password','adult_attested':True})
    assert register.status_code==503 and register.json()['code']=='auth_unavailable'
