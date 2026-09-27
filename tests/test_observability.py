import json
import os
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault('IYOSI_SECRET','test-secret-0123456789-0123456789')
from api.main import app


def test_request_and_provider_failure_logs_omit_query_and_identifiers(caplog, monkeypatch):
    monkeypatch.delenv('GEOCODER_URL',raising=False)
    with caplog.at_level('INFO',logger='uvicorn.error'):
        response=TestClient(app).get('/v1/address-suggestions',params={'q':'private search phrase'})
    assert response.status_code==503
    events=[json.loads(record.message) for record in caplog.records if record.message.startswith('{')]
    failure=next(event for event in events if event['event']=='geocoder_failure')
    request=next(event for event in events if event['event']=='request_complete')
    assert failure['reason']=='not_configured'
    assert request['route']=='/v1/address-suggestions'
    assert request['status']==503
    assert request['request_id']==failure['request_id']==response.headers['X-Request-ID']
    assert request['duration_ms']>=0
    assert 'private search phrase' not in '\n'.join(record.message for record in caplog.records)


def test_upstream_timeout_is_countable_without_logging_search_text(caplog, monkeypatch):
    from api import main
    monkeypatch.setenv('GEOCODER_URL','https://example.invalid/geocode')
    monkeypatch.setattr(main,'check_rate',lambda *_: None)
    @contextmanager
    def fake_db():
        yield object()
    monkeypatch.setattr(main,'db',fake_db)
    def timeout(*args,**kwargs):
        raise httpx.ReadTimeout('upstream timeout')
    monkeypatch.setattr(main.httpx,'get',timeout)
    with caplog.at_level('INFO',logger='uvicorn.error'):
        response=TestClient(app).get('/v1/address-suggestions',params={'q':'another private phrase'})
    assert response.status_code==503
    event=next(json.loads(record.message) for record in caplog.records if 'geocoder_failure' in record.message)
    assert event['reason']=='ReadTimeout'
    assert event['provider_status'] is None
    assert event['request_id']==response.headers['X-Request-ID']
    assert 'another private phrase' not in '\n'.join(record.message for record in caplog.records)


def test_benchmark_refuses_a_non_test_database():
    from scripts.benchmark_viewports import require_test_db
    with pytest.raises(SystemExit,match='ending in _test'):
        require_test_db('postgresql://iyosi:password@localhost:5432/iyosi')
