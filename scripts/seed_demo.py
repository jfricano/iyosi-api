"""Publish unmistakably fictional places through the API in iyosi_demo only."""

import json
import os
import secrets
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from api.core import sign
from api.main import app


DATABASE_URL = os.environ.get('DATABASE_URL', '')
FIXTURES = Path(__file__).resolve().parents[1] / 'infra/demo/places.json'


def require_demo_database() -> None:
    if os.environ.get('IYOSI_DEMO_SEED') != '1':
        raise SystemExit('Set IYOSI_DEMO_SEED=1 to seed the isolated demo database')
    with psycopg.connect(DATABASE_URL) as conn:
        name = conn.execute('SELECT current_database()').fetchone()[0]
        if name != 'iyosi_demo':
            raise SystemExit(f'Refusing to seed {name}; only iyosi_demo is allowed')
        if not conn.execute('SELECT 1 FROM ncr_boundary WHERE id=1').fetchone():
            raise SystemExit('Migrate and load the NCR boundary before seeding')


def ensure_account(client: TestClient, email: str) -> str:
    with psycopg.connect(DATABASE_URL) as conn:
        existing = conn.execute('SELECT id FROM accounts WHERE email=%s', (email,)).fetchone()
    if existing:
        return existing[0]
    response = client.post('/v1/auth/register', json={
        'email': email,
        'password': secrets.token_urlsafe(24),
        'adult_attested': True,
    })
    if response.status_code != 201:
        raise RuntimeError(f'Demo account registration failed: {response.status_code} {response.text}')
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute('SELECT id FROM accounts WHERE email=%s', (email,)).fetchone()[0]


def main() -> None:
    require_demo_database()
    places = json.loads(FIXTURES.read_text())
    with TestClient(app) as client:
        contributor_id = ensure_account(client, 'demo-contributor@iyosi.invalid')
        administrator_id = ensure_account(client, 'demo-admin@iyosi.invalid')
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("UPDATE accounts SET role='admin' WHERE id=%s", (administrator_id,))
        contributor = {'Authorization': f'Bearer {sign(contributor_id)}'}
        administrator = {'Authorization': f'Bearer {sign(administrator_id)}'}

        for fixture in places:
            with psycopg.connect(DATABASE_URL) as conn:
                existing = conn.execute('SELECT id FROM places WHERE name=%s', (fixture['name'],)).fetchone()
            if existing:
                print('Already present:', fixture['name'], existing[0])
                continue
            payload = {
                'intent': 'create',
                'name': fixture['name'],
                'kind': fixture['kind'],
                'location': {'lat': fixture['lat'], 'lon': fixture['lon']},
                'address_label': 'Synthetic development coordinate in Metro Manila',
                'access_notes': 'Fictional development record. Do not use as a real smoking location.',
                'inside_venue': fixture['inside_venue'],
                'basis': 'Synthetic development fixture; no real smoking-area claim or evidence.',
            }
            submission = client.post('/v1/place-submissions', json=payload,
                                     headers={**contributor, 'Idempotency-Key': secrets.token_hex(16)})
            if submission.status_code != 201:
                raise RuntimeError(f'Demo submission failed: {submission.status_code} {submission.text}')
            submission_id = submission.json()['id']
            with psycopg.connect(DATABASE_URL) as conn:
                case_id = conn.execute("SELECT id FROM moderation_cases WHERE source_type='submission' AND source_id=%s", (submission_id,)).fetchone()[0]
            decision = client.post(f'/v1/admin/moderation-cases/{case_id}/decisions',
                                   json={'action': 'publish', 'reason': 'Synthetic development fixture only'},
                                   headers=administrator)
            if decision.status_code != 201:
                raise RuntimeError(f'Demo publication failed: {decision.status_code} {decision.text}')
            print('Published demo place:', fixture['name'])


if __name__ == '__main__':
    main()
