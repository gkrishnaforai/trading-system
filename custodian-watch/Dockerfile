# custodian-watch — external container-health supervisor.
# Deliberately minimal: stdlib for docker API + sqlite; psycopg2 only
# for the best-effort mirror into the shared incidents table.
FROM python:3.11-slim

RUN pip install --disable-pip-version-check --no-cache-dir psycopg2-binary==2.9.10

WORKDIR /app
COPY custodian-watch/watcher.py .

# sqlite state lives on the named volume at /data
VOLUME /data

CMD ["python", "-u", "watcher.py"]
