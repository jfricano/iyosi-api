"""Print privacy-safe pilot operations gauges for an operator scheduler."""
import json

from api.core import db


def snapshot(conn):
    queue = conn.execute("""SELECT
        count(*) FILTER (WHERE state='open')::int AS open_cases,
        count(*) FILTER (WHERE state='open' AND priority>=2)::int AS urgent_open_cases,
        coalesce(extract(epoch FROM now()-min(created_at) FILTER (WHERE state='open'))::int,0) AS oldest_open_seconds,
        count(*) FILTER (WHERE state='resolved' AND resolved_at>=now()-interval '24 hours')::int AS resolved_24h
        FROM moderation_cases""").fetchone()
    size = conn.execute('SELECT pg_database_size(current_database()) AS database_bytes').fetchone()
    return {'open_cases':queue['open_cases'],'urgent_open_cases':queue['urgent_open_cases'],
            'oldest_open_seconds':queue['oldest_open_seconds'],'resolved_24h':queue['resolved_24h'],
            'database_bytes':size['database_bytes']}


if __name__ == '__main__':
    with db() as connection:
        print(json.dumps(snapshot(connection),sort_keys=True))
