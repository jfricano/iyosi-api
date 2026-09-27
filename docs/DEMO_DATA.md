# Isolated synthetic data for iOS development

This stack exposes a second API at `http://localhost:8001` with four **fictional** place records, one for each place kind. It uses a separate `iyosi_demo` PostGIS database and a tiny local GeoJSON search service. No record represents an actual smoking area, and none is verified. The normal API and pilot database remain separate.

From the API repository, with `.env` configured:

```sh
docker compose -f compose.yaml -f compose.demo.yaml up -d --build demo_api
docker compose -f compose.yaml -f compose.demo.yaml exec -e IYOSI_DEMO_SEED=1 demo_api sh -c 'PYTHONPATH=. python scripts/seed_demo.py'
```

Point the iOS Simulator's API setting to `http://localhost:8001`. Search for `DEMO` or a city in a fixture name. The four pins appear around Manila, Quezon City, Makati, and Taguig. The seeder uses the same registration, submission, and admin-decision API paths as normal contributions; running it again skips existing names. It refuses any database other than `iyosi_demo` and requires `IYOSI_DEMO_SEED=1`.

Inspect the public response:

```sh
curl 'http://localhost:8001/v1/places?bbox=120.8,14.4,121.2,14.8'
curl 'http://localhost:8001/v1/address-suggestions?q=DEMO'
```

Remove the demo stack and its synthetic data when no longer needed:

```sh
docker compose -f compose.yaml -f compose.demo.yaml stop demo_api demo_geocoder demo_db
docker compose -f compose.yaml -f compose.demo.yaml rm -f demo_api demo_geocoder demo_db
docker volume rm iyosi_demo_postgres_data
```

Real pilot places need source and evidence review before publication. They do not come from this fixture set.
