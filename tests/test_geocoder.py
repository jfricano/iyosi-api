import os
from contextlib import contextmanager

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault('IYOSI_SECRET', 'test-secret-0123456789-0123456789')

from api import main


@contextmanager
def fake_db():
    yield object()


def setup_geocoder(monkeypatch, payload, *, key=None):
    monkeypatch.setattr(main, 'db', fake_db)
    monkeypatch.setattr(main, 'check_rate', lambda *_: None)
    monkeypatch.setattr(main, 'within_ncr', lambda _conn, lon, lat: 120.9 < lon < 121.2 and 14.4 < lat < 14.8)
    monkeypatch.delenv('GEOAPIFY_API_KEY', raising=False)
    monkeypatch.setenv('GEOCODER_URL', 'http://local-geocoder/search')
    if key:
        monkeypatch.setenv('GEOAPIFY_API_KEY', key)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=payload, request=httpx.Request('GET', url))

    monkeypatch.setattr(main.httpx, 'get', get)
    return calls


def test_geoapify_filters_and_normalizes_without_leaking_key(monkeypatch):
    features = [
        {'geometry': {'type': 'Point', 'coordinates': [121.03, 14.60]}, 'properties': {'formatted': 'Quezon City, Metro Manila'}},
        {'geometry': {'type': 'Point', 'coordinates': [122.0, 14.60]}, 'properties': {'formatted': 'Outside NCR'}},
        {'geometry': {'type': 'Point', 'coordinates': ['NaN', 14.60]}, 'properties': {'formatted': 'Bad point'}},
    ]
    calls = setup_geocoder(monkeypatch, {'features': features}, key='private-test-key')
    response = TestClient(main.app).get('/v1/address-suggestions', params={'q': 'Quezon'})
    assert response.status_code == 200
    assert response.json() == {'items': [{'label': 'Quezon City, Metro Manila', 'location': {'lat': 14.6, 'lon': 121.03}}], 'provider': 'geoapify'}
    assert 'private-test-key' not in str(response.json())
    assert calls[0][0] == 'https://api.geoapify.com/v1/geocode/autocomplete'
    assert calls[0][1]['headers'] == {'x-api-key': 'private-test-key'}
    assert calls[0][1]['params']['filter'] == 'countrycode:ph'
    assert calls[0][1]['params']['text'] == 'Quezon'


def test_demo_geocoder_and_malformed_provider(monkeypatch):
    calls = setup_geocoder(monkeypatch, {'features': [{'geometry': {'type': 'Point', 'coordinates': [121.02, 14.55]}, 'properties': {'name': 'DEMO ONLY'}}]})
    client = TestClient(main.app)
    response = client.get('/v1/address-suggestions?q=DEMO')
    assert response.status_code == 200
    assert response.json()['items'][0]['label'] == 'DEMO ONLY'
    assert response.json()['provider'] is None
    assert calls[0][1]['params'] == {'q': 'DEMO', 'limit': 5}

    setup_geocoder(monkeypatch, {'features': 'invalid'})
    failure = client.get('/v1/address-suggestions?q=DEMO')
    assert failure.status_code == 503
    assert failure.json()['code'] == 'geocoder_unavailable'
    assert failure.json()['request_id'] == failure.headers['X-Request-ID']


def test_provider_timeout_is_safe(monkeypatch):
    setup_geocoder(monkeypatch, {})

    def timeout(*_args, **_kwargs):
        raise httpx.TimeoutException('provider timeout')

    monkeypatch.setattr(main.httpx, 'get', timeout)
    response = TestClient(main.app).get('/v1/address-suggestions?q=Manila')
    assert response.status_code == 503
    assert 'provider timeout' not in response.text
