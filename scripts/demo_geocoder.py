"""Tiny GeoJSON search service for the isolated local demo environment."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


FIXTURES = json.loads((Path(__file__).resolve().parents[1] / 'infra/demo/places.json').read_text())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != '/search':
            self.send_error(404)
            return
        query = parse_qs(parsed.query).get('q', [''])[0].casefold().strip()
        matches = [place for place in FIXTURES if query and query in place['name'].casefold()][:5]
        body = json.dumps({'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [place['lon'], place['lat']]},
             'properties': {'name': place['name']}}
            for place in matches
        ]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/geo+json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
