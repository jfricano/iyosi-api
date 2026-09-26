"""Load a reviewed NCR GeoJSON polygon (Feature or geometry) into PostGIS."""
import json, os, sys
import psycopg

item = json.load(open(sys.argv[1]))
if item['type'] == 'FeatureCollection':
    matches = [f for f in item['features'] if 'NCR' in str(f.get('properties', {})) or 'National Capital Region' in str(f.get('properties', {}))]
    if len(matches) != 1:
        raise SystemExit(f'Expected one NCR feature, got {len(matches)}')
    item = matches[0]
geom = item.get('geometry', item)
if geom['type'] not in ('Polygon', 'MultiPolygon'):
    raise SystemExit('Boundary must be Polygon or MultiPolygon')
source = sys.argv[2]
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute("INSERT INTO ncr_boundary(id,geom,source) VALUES (1,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),%s) ON CONFLICT (id) DO NOTHING", (json.dumps(geom),source))
