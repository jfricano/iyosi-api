"""The edge proxy is the only peer allowed to supply a visitor address."""
import asyncio
import os
import subprocess
from pathlib import Path

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def observed_client(peer, forwarded):
    seen = []

    async def app(scope, _receive, _send):
        seen.append(scope['client'][0])

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(_message):
        pass

    scope = {
        'type': 'http',
        'client': (peer, 12345),
        'scheme': 'http',
        'headers': [(b'x-forwarded-for', forwarded.encode()), (b'x-forwarded-proto', b'https')],
    }
    asyncio.run(ProxyHeadersMiddleware(app, trusted_hosts='10.55.0.2')(scope, receive, send))
    return seen[0], scope['scheme']


def test_only_exact_ingress_peer_can_set_client_address():
    assert observed_client('10.55.0.2', '198.51.100.99, 203.0.113.7') == ('203.0.113.7', 'https')
    assert observed_client('10.55.0.3', '198.51.100.99') == ('10.55.0.3', 'http')


def test_runtime_refuses_trust_everyone():
    env = {**os.environ, 'IYOSI_TRUSTED_PROXY_IPS': '*'}
    result = subprocess.run(['sh', 'scripts/serve_api.sh'], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'Refusing to trust' in result.stderr
