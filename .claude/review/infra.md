# Infrastructure, configuration and docs checklist

Source tags are explained in `standards-sources.md`. Allowed checks: `docker compose config` (also with
`--profile observability`), reading files. Never start, stop or build containers.

## Docker and Compose
- [ ] Images are pinned to specific versions (not `latest`); a digest is stronger. [Docker]
- [ ] Is there a Dockerfile for the backend? If not, say so and weigh it: a one-command run for reviewers is nice, but adding one late is a medium-sized task; recommend only if time allows.
- [ ] If there is a Dockerfile: multi-stage, `.dockerignore`, non-root `USER`, small base, `COPY` over `ADD`, no secrets baked in. [Docker]
- [ ] Services have healthchecks where order matters (the database has one); `depends_on` uses health where the app needs the database. (Healthchecks are not on the Docker best-practices page: own knowledge.)
- [ ] Volumes keep database data; credentials in Compose are demo-only and the README says so; ports are not exposed more widely than needed.
- [ ] Optional services (Prometheus, Grafana) are in a profile so the default `docker compose up` stays small.

## Configuration (12-factor)
- [ ] All settings come from the environment, with safe development defaults and guards for dangerous ones (secret length, `APP_ENV`). [12F: config]
- [ ] `.env.example` lists every setting the code reads (compare against `app/config.py`), with comments.
- [ ] Logs go to stdout as a stream; JSON by default. [12F: logs]
- [ ] Start order is documented and works from a clean checkout: database up, migrations, seed, server. A new migration does not break a database that already has rows.
- [ ] Dev/prod parity: tests use a separate database; nothing in tests wipes the demo data.

## Prometheus and Grafana
- [ ] Metric names have the app prefix, base units and `_total` / `_seconds` suffixes; labels hold only bounded values (route template, request type, tool name, outcome). No user id, conversation id or free text as a label. [Prom: naming, instrumentation]
- [ ] Histograms have buckets that cover the real range (model calls take seconds, SQL statements milliseconds); p50/p95 are computed in queries with `histogram_quantile`. [Prom: histograms]
- [ ] Failures are counted with attempts so a ratio can be computed; series exist with a default 0 where a dashboard divides by them. [Prom: instrumentation]
- [ ] The Grafana dashboard JSON is valid, its datasource uid matches the provisioned one, and each panel has a unit. (Queries were verified against real data on Day 3; re-verify only if metrics were renamed.)
- [ ] Memory and CPU come from the process collector and work on the platform in use.

## README and docs accuracy
- [ ] Run instructions work from a clean checkout (commands, ports, order). Demo accounts match `seed/world.py`.
- [ ] Architecture description and "how to swap the data source" match the code (`app/container.py`).
- [ ] Numbers in the README are measured and say how (machine, load, date). Anything estimated is labelled as such. Load-test results and capacity estimate exist when the milestone calls for them.
- [ ] Test counts and screenshots in the docs are current. Known limitations are listed honestly (including deferred items from `CLAUDE.md`).
- [ ] `.gitignore` covers `.env`, `.venv`, `node_modules`, `__pycache__`, build output; no large or private files (screenshots of a personal desktop, exported data) are committed.
