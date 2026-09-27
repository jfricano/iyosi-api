from contextlib import contextmanager

from fastapi.testclient import TestClient

from api import main
from api.core import admin


def test_admin_page_serves_with_private_view_protections():
    client = TestClient(main.app)
    response = client.get('/admin')
    assert response.status_code == 200
    assert 'Moderation queue' in response.text
    assert 'no-store' in response.headers['cache-control']
    assert "default-src 'none'" in response.headers['content-security-policy']
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert client.get('/admin/assets/admin.js').status_code == 200
    assert '/admin' not in client.get('/openapi.json').json()['paths']


def test_case_detail_requires_authentication():
    response = TestClient(main.app).get('/v1/admin/moderation-cases/case_one')
    assert response.status_code == 401
    assert response.json()['code'] == 'unauthenticated'


class FakeConn:
    def __init__(self, source_type):
        self.source_type = source_type

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        return self

    def fetchone(self):
        query = self.query
        if 'FROM moderation_cases' in query:
            return {'id': 'case_one', 'source_type': self.source_type, 'source_id': 'sub_one' if self.source_type == 'submission' else 'report_one', 'state': 'open', 'priority': 1}
        if 'FROM place_submissions' in query and 'ST_Y' not in query:
            return {'id': 'sub_one', 'intent': 'correct', 'place_id': 'plc_one', 'name': 'Proposed', 'account_id': 'acct_private', 'basis': 'Private source', 'location': 'binary geometry', 'access_point': None}
        if 'FROM place_submissions' in query and 'ST_Y' in query:
            return {'lat': 14.6, 'lon': 121.0, 'access_lat': None, 'access_lon': None}
        if 'FROM reports' in query:
            return {'id': 'report_one', 'target_type': 'review', 'target_id': 'rev_one', 'detail': 'Private complaint', 'account_id': 'acct_private'}
        if 'FROM reviews' in query:
            return {'id': 'rev_one', 'place_id': 'plc_one', 'stars': 1, 'body': 'Review text', 'hidden_at': None, 'deleted_at': None}
        if 'FROM places' in query:
            return {'id': 'plc_one', 'name': 'Current', 'kind': 'venue_designated', 'advisory_status': 'community_reported', 'publication_state': 'published', 'version': 7, 'verification_evidence': None, 'lat': 14.6, 'lon': 121.0}
        raise AssertionError(query)

    def fetchall(self):
        assert 'FROM moderation_decisions' in self.query
        return [{'id': 'dec_one', 'action': 'resolve', 'reason': 'Earlier action', 'old_state': {}, 'new_state': {}}]


def test_case_detail_supplies_current_place_version_for_correction(monkeypatch):
    @contextmanager
    def fake_db():
        yield FakeConn('submission')

    monkeypatch.setattr(main, 'db', fake_db)
    main.app.dependency_overrides[admin] = lambda: {'id': 'acct_admin'}
    try:
        response = TestClient(main.app).get('/v1/admin/moderation-cases/case_one')
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body['source']['location'] == {'lat': 14.6, 'lon': 121.0}
    assert body['context']['place']['version'] == 7
    assert body['source']['basis'] == 'Private source'
    assert body['decisions'][0]['action'] == 'resolve'


def test_review_report_context_includes_review_and_place(monkeypatch):
    @contextmanager
    def fake_db():
        yield FakeConn('report')

    monkeypatch.setattr(main, 'db', fake_db)
    main.app.dependency_overrides[admin] = lambda: {'id': 'acct_admin'}
    try:
        response = TestClient(main.app).get('/v1/admin/moderation-cases/case_one')
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()['context']['review']['id'] == 'rev_one'
    assert response.json()['context']['place']['id'] == 'plc_one'
