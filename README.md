# Donate – 24/7 Multicanal Streaming (GCP)

Live streaming pipeline for **YouTube Live**: Terraform-provisioned GCP infra (Compute Engine, Cloud SQL PostgreSQL), Nginx-RTMP ingest, and Python workers for demux, overlay (Top 10 donor ranking + PIX alerts), PTS/DTS continuity, and H.264 encode.

## Quick start

1. **Infrastructure**: `cd terraform/environments/prod && cp terraform.tfvars.example terraform.tfvars` (set `project_id`), then `terraform init && terraform plan -var-file=terraform.tfvars && terraform apply`.
2. **Config**: Create `docker/.env` with `CLOUD_SQL_CONNECTION_NAME`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (and optional YouTube Live push URL).
3. **DB schema**: `python scripts/init_db.py` (with DB_* env set, or uses default SQLite for local dev).
4. **Run**: `cd docker && docker compose up -d`. Ingest RTMP at `rtmp://<host>:1935/live/`.

See [specs/001-gcp-streaming-infra/quickstart.md](specs/001-gcp-streaming-infra/quickstart.md) for full steps.

## Encoding (YouTube Live)

- CBR 4500 kbps, GOP 2 s, H.264 profile high, level 4.1, tune zerolatency.
- Configured in `src/config/settings.py` (EncodingSettings); override via env (e.g. `ENCODING__cbr_bitrate_k`) or `.env`.

## Overlay data

- **Read**: Workers read ranking and PIX alerts from the DB (atomic snapshot) every ~8 s; on DB unreachable they keep the last known overlay.
- **Write**: Internal API in `src/overlay_api/` (e.g. `POST /donors`, `POST /alerts`, `POST /ranking`) writes to the same database. Run with Flask: `FLASK_APP=src/overlay_api/app.py flask run --port 5000`.

## Environment variables

All app config is in `src/config/settings.py` (Pydantic Settings). Use a **double underscore** between section and key: `SECTION__key`. Optional `.env` in project root is loaded automatically.

| Variable | Description |
|----------|-------------|
| `DB__host`, `DB__port`, `DB__name` | Database connection (defaults: 127.0.0.1, 5432, donate) |
| `DB__user`, `DB__password` | Credentials; empty `DB__user` => SQLite `overlay.db` |
| `API__host`, `API__port` | Overlay API bind (defaults: 0.0.0.0, 5001) |
| `ENCODING__*` | Encoding defaults (cbr_bitrate_k, fps, gop_frames, profile, level, tune, encoder, default_width, default_height) |
| `WORKER__overlay_refresh_interval_seconds`, `WORKER__default_input_url` | Overlay refresh interval (default 8), default RTSP/input URL |

See `.env.example` for a full list.

## Repo layout

- `terraform/` – GCP modules (network, compute, cloud-sql, iam) and prod environment.
- `docker/` – Docker Compose, Nginx-RTMP config, Cloud SQL Auth Proxy.
- `src/stream_workers/` – Demux, overlay, PTS/DTS, encode, DB read.
- `src/overlay_api/` – Internal API for overlay data writes.
- `src/config/` – Centralized Pydantic Settings (DB, encoding, API, worker).
- `specs/001-gcp-streaming-infra/` – Feature spec, plan, tasks, contracts.
