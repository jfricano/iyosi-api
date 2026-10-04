import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout
from fastapi import Depends, Header, HTTPException, Request

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://iyosi:local-development-only@localhost:5432/iyosi')
SECRET = os.environ.get('IYOSI_SECRET', '')

def uid(prefix: str) -> str:
    return prefix + '_' + secrets.token_hex(12)

POOL_MAX = int(os.environ.get('IYOSI_DB_POOL_MAX', '10'))
_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

def _get_pool() -> ConnectionPool:
    # Opened lazily so imports (OpenAPI export, tests that repoint DATABASE_URL) never connect.
    global _pool
    with _pool_lock:
        if _pool is not None and _pool.conninfo != DATABASE_URL:
            _pool.close()
            _pool = None
        if _pool is None:
            _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=POOL_MAX, timeout=10,
                                   kwargs={'row_factory': dict_row}, check=ConnectionPool.check_connection,
                                   name='iyosi', open=True)
        return _pool

def close_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None

@contextmanager
def db():
    # Same transaction semantics as psycopg.connect(): commit on success, roll back on error.
    try:
        with _get_pool().connection() as conn:
            yield conn
    except PoolTimeout:
        fail(503, 'database_busy', 'Service is busy; try again shortly')

def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail={'code': code, 'message': message})

def utcnow():
    return datetime.now(timezone.utc)

def auth_configured():
    if len(SECRET) < 32:
        fail(503, 'auth_unavailable', 'Authentication is not configured')

TOKEN_TTL_SECONDS = 86400

def sign(account_id: str, exp: int | None = None) -> str:
    auth_configured()
    exp = exp if exp is not None else int(time.time()) + TOKEN_TTL_SECONDS
    payload = base64.urlsafe_b64encode(json.dumps({'sub': account_id, 'exp': exp}, separators=(',', ':')).encode()).decode().rstrip('=')
    mac = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + mac

def token_body(account_id: str) -> dict:
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    return {'access_token': sign(account_id, exp), 'token_type': 'bearer', 'expires_at': datetime.fromtimestamp(exp, timezone.utc)}

def account(authorization: str | None = Header(default=None)) -> dict:
    auth_configured()
    if not authorization or not authorization.startswith('Bearer '):
        fail(401, 'unauthenticated', 'Sign in to continue')
    try:
        payload, mac = authorization[7:].split('.', 1)
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if data['exp'] < time.time():
            raise ValueError()
        with db() as conn:
            row = conn.execute('SELECT id,email,role,adult_attested_at FROM accounts WHERE id=%s AND disabled_at IS NULL', (data['sub'],)).fetchone()
        if row:
            return row
    except (ValueError, KeyError, IndexError, json.JSONDecodeError, binascii.Error):
        pass
    fail(401, 'unauthenticated', 'Sign in to continue')

def admin(user: dict = Depends(account)) -> dict:
    if user['role'] != 'admin':
        fail(403, 'forbidden', 'Admin access required')
    return user

def hash_password(password: str, salt: bytes | None = None):
    salt = salt or secrets.token_bytes(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ':' + result.hex()

def password_valid(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split(':')
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split(':')[1], digest)
    except (ValueError, TypeError):
        return False

def check_rate(conn, bucket: str, limit: int, seconds: int):
    # Bucket keys are HMACs; no raw IP or location is stored.
    row = conn.execute("""INSERT INTO rate_buckets(bucket,count,expires_at)
                       VALUES (%s,1,now()+(%s || ' seconds')::interval)
                       ON CONFLICT(bucket) DO UPDATE SET
                         count=CASE WHEN rate_buckets.expires_at<=now() THEN 1 ELSE rate_buckets.count+1 END,
                         expires_at=CASE WHEN rate_buckets.expires_at<=now() THEN EXCLUDED.expires_at ELSE rate_buckets.expires_at END
                       RETURNING count""", (bucket,seconds)).fetchone()
    if row['count'] > limit:
        fail(429, 'rate_limited', 'Please try again later')

def client_bucket(request: Request, name: str) -> str:
    ip = request.client.host if request.client else 'unknown'
    return hmac.new(SECRET.encode(), (name + ':' + ip).encode(), hashlib.sha256).hexdigest()

def idempotent_lookup(conn, user_id: str, route: str, key: str | None, payload: Any):
    if not key:
        fail(400, 'idempotency_required', 'Idempotency-Key header is required')
    if len(key) > 128 or len(key) < 8:
        fail(422, 'invalid_idempotency_key', 'Idempotency-Key must be 8 to 128 characters')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (user_id+':'+route+':'+key,))
    row = conn.execute('SELECT request_hash,response_body FROM idempotency_records WHERE account_id=%s AND route=%s AND key=%s AND created_at>now()-interval \'24 hours\' FOR UPDATE', (user_id,route,key)).fetchone()
    if row:
        if row['request_hash'] != digest:
            fail(409, 'idempotency_conflict', 'Key was used with different content')
        return digest, row['response_body']
    return digest, None

def idempotent_store(conn, user_id, route, key, digest, body, status=201):
    conn.execute('DELETE FROM idempotency_records WHERE account_id=%s AND route=%s AND key=%s', (user_id,route,key))
    conn.execute('INSERT INTO idempotency_records(account_id,route,key,request_hash,response_status,response_body) VALUES (%s,%s,%s,%s,%s,%s)', (user_id,route,key,digest,status,json.dumps(body,default=str)))

def cursor_encode(value: str):
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')

def cursor_decode(value: str | None):
    if not value:
        return ''
    try:
        decoded = base64.b64decode(value + '=' * (-len(value)%4), altchars=b'-_', validate=True).decode()
        if len(decoded) > 100:
            raise ValueError()
        return decoded
    except (ValueError, UnicodeDecodeError, binascii.Error):
        fail(400, 'invalid_cursor', 'Invalid cursor')

def keyset_encode(at: datetime, item_id: str):
    return cursor_encode(at.isoformat() + '|' + item_id)

def keyset_decode(value: str | None):
    # Newest-first pages resume after (timestamp, id); an empty cursor starts at the top.
    decoded = cursor_decode(value)
    if not decoded:
        return None
    try:
        at, item_id = decoded.rsplit('|', 1)
        parsed = datetime.fromisoformat(at)
        if parsed.tzinfo is None or not item_id:
            raise ValueError()
        return parsed, item_id
    except ValueError:
        fail(400, 'invalid_cursor', 'Invalid cursor')

def point(lon, lat):
    return f'SRID=4326;POINT({lon} {lat})'

def within_ncr(conn, lon, lat):
    row = conn.execute('SELECT ST_Covers(geom,ST_SetSRID(ST_MakePoint(%s,%s),4326)) AS inside FROM ncr_boundary WHERE id=1', (lon,lat)).fetchone()
    if not row:
        fail(503, 'boundary_unavailable', 'NCR boundary is not configured')
    return row['inside']
