# Postgres 16 + PostGIS 3.5 + pgvector (02 §3). The PostGIS image does not ship pgvector;
# the PGDG apt repository it already configures does.
FROM postgis/postgis:16-3.5
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*
COPY init/ /docker-entrypoint-initdb.d/
