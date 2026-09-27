FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --home /app iyosi

COPY --chown=iyosi:iyosi api /app/api
COPY --chown=iyosi:iyosi admin /app/admin
COPY --chown=iyosi:iyosi scripts /app/scripts
COPY --chown=iyosi:iyosi migrations /app/migrations
COPY --chown=iyosi:iyosi infra/db/ncr_boundary.geojson /app/infra/db/ncr_boundary.geojson

USER iyosi
EXPOSE 8000
CMD ["sh", "scripts/start_api.sh"]
