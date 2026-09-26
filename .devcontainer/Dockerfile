FROM python:3.12-slim-bookworm

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends git postgresql-client \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt /tmp/iyosi-requirements.txt
RUN pip install --no-cache-dir -r /tmp/iyosi-requirements.txt
