# Donatik Tube – 24/7 streaming on GCP

Live streaming pipeline for **YouTube Live**: Terraform-provisioned GCP infrastructure (Compute Engine, Cloud SQL PostgreSQL), Nginx-RTMP ingest, and Python workers for demux, overlay (Top 10 donor ranking + PIX alerts), PTS/DTS continuity, and H.264 encode.

This guide explains everything you need to deploy the stack on Google Cloud Platform.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [GCP project setup](#gcp-project-setup)
3. [Deploy infrastructure with Terraform](#deploy-infrastructure-with-terraform)
4. [Cloud SQL: create user and get connection details](#cloud-sql-create-user-and-get-connection-details)
5. [Configuration and secrets](#configuration-and-secrets)
6. [Initialize the database](#initialize-the-database)
7. [Run the stack (Docker Compose)](#run-the-stack-docker-compose)
8. [Ingest stream and push to YouTube Live](#ingest-stream-and-push-to-youtube-live)
9. [Overlay API and data](#overlay-api-and-data)
10. [Architecture summary](#architecture-summary)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **GCP account** with billing enabled.
- **gcloud CLI** installed and authenticated: `gcloud auth login` and `gcloud config set project YOUR_PROJECT_ID`.
- **Terraform** ≥ 1.x ([install](https://developer.hashicorp.com/terraform/downloads)).
- **Docker** and **Docker Compose** (for running Nginx-RTMP, workers, and Cloud SQL Auth Proxy).
- **Python 3.11+** and **uv** (optional, for local runs and `scripts/init_db.py`).

---

## GCP project setup

1. Create or select a GCP project and note the **project ID**.

2. Enable required APIs:

   ```bash
   gcloud services enable compute.googleapis.com
   gcloud services enable sqladmin.googleapis.com
   gcloud services enable iam.googleapis.com
   ```

3. Ensure billing is linked to the project (required for Compute Engine and Cloud SQL).

---

## Deploy infrastructure with Terraform

Terraform creates:

- **VPC** and subnet (ingress allowed only on ports **1935** RTMP and **554** RTSP).
- **Cloud SQL PostgreSQL** with private IP only (no public IP).
- **Compute Engine VM** (Debian 12) with a service account that has Cloud SQL Client and Logging.
- **IAM** service account for the VM.

Steps:

1. Go to the prod environment:

   ```bash
   cd terraform/environments/prod
   ```

2. Copy the example tfvars and set your project ID (and optionally region/zone):

   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars:
   #   project_id = "your-gcp-project-id"
   #   region     = "us-central1"   # optional
   #   zone       = "us-central1-a" # optional
   ```

3. Initialize and apply:

   ```bash
   terraform init
   terraform plan -var-file=terraform.tfvars
   terraform apply -var-file=terraform.tfvars
   ```

4. Save the outputs; you will need the Cloud SQL connection name and (optionally) the VM private IP:

   ```bash
   terraform output cloud_sql_connection_name   # e.g. project-id:region:streaming-db
   terraform output compute_network_ip         # private IP of the VM
   ```

The state file is stored locally in `terraform/environments/prod/terraform.tfstate`. For production, consider a remote backend (GCS + state locking).

---

## Cloud SQL: create user and get connection details

The Cloud SQL instance has **private IP only**. To connect you either:

- Run the **Cloud SQL Auth Proxy** (recommended for local or Docker), or
- Connect from the **VM** in the same VPC using the instance **private IP**.

1. Create a database user and set a password (if not already done). You can use the GCP Console (Cloud SQL → Users) or `gcloud sql users create`:

   ```bash
   gcloud sql users create YOUR_DB_USER \
     --instance=streaming-db \
     --password=YOUR_SECURE_PASSWORD
   ```

   The database name created by Terraform is `donate` (or the value of `db_name` in the Cloud SQL module).

2. **Connection name** (for Auth Proxy): use the Terraform output:

   - `terraform output cloud_sql_connection_name` → value like `your-project:us-central1:streaming-db`.

3. **Private IP** (for connections from the VM): use Terraform output from the Cloud SQL module, or:

   - GCP Console → Cloud SQL → your instance → **Private IP**.

---

## Configuration and secrets

All application settings are centralized in **Pydantic Settings** (`src/config/settings.py`). Environment variables use the form **`SECTION__key`** (double underscore). A `.env` file in the project root is loaded automatically.

### For Docker Compose (recommended for deployment)

Create a `.env` file in the **`docker/`** directory (or where you run `docker compose`). The Compose file uses `env_file: .env` for the worker and the Cloud SQL Proxy.

Required for the **Cloud SQL Auth Proxy** (used by Compose):

```bash
# docker/.env
CLOUD_SQL_CONNECTION_NAME=your-project:region:streaming-db
```

Required for the **app** (database and API):

```bash
# Database (app reads DB__* with Pydantic Settings)
DB__host=cloud-sql-auth
DB__port=5432
DB__name=donate
DB__user=YOUR_DB_USER
DB__password=YOUR_SECURE_PASSWORD

# Overlay API (optional; defaults are 0.0.0.0 and 5001)
API__host=0.0.0.0
API__port=5001
```

- **`DB__host=cloud-sql-auth`** is the Docker Compose service name of the Cloud SQL Proxy; the worker and overlay API connect to it on port 5432.

If you run the stack **on the GCP VM** and use the Cloud SQL **private IP** instead of the proxy, set:

```bash
DB__host=<Cloud SQL private IP>
DB__port=5432
DB__name=donate
DB__user=...
DB__password=...
```

and do **not** start the `cloud-sql-auth` service (or use a separate compose override).

### Full list of optional env vars

See **`.env.example`** at the repo root for all supported keys (`DB__*`, `API__*`, `ENCODING__*`, `WORKER__*`).

---

## Initialize the database

Create the schema (tables for donors, ranking, PIX alerts) once before running the app.

**Option A – Local with Auth Proxy**

1. Start only the Cloud SQL Proxy (e.g. in `docker/` with the same `.env`):

   ```bash
   docker compose up -d cloud-sql-auth
   ```

2. From the repo root, with `DB__*` set (e.g. in a `.env` in the repo root or exported), run:

   ```bash
   uv run python scripts/init_db.py
   ```

   If `DB__user` is empty, the app uses SQLite (`overlay.db`) and no proxy is needed.

**Option B – On the VM**

1. Copy your `.env` (with `DB__*` and, if using proxy, `CLOUD_SQL_CONNECTION_NAME`) to the VM.
2. Run the proxy (if used) and then:

   ```bash
   uv run python scripts/init_db.py
   ```

   Or run `init_db.py` inside a worker container that shares the same network as the proxy.

---

## Run the stack (Docker Compose)

From the **`docker/`** directory (with the same `.env` that has `CLOUD_SQL_CONNECTION_NAME` and `DB__*`):

```bash
cd docker
docker compose up -d
```

This starts:

- **nginx-rtmp** – RTMP ingest on port **1935** (application `live`).
- **worker** – Python stream worker (demux, overlay, encode); reads overlay data from the DB.
- **cloud-sql-auth** – Cloud SQL Auth Proxy; worker and overlay API use it when `DB__host=cloud-sql-auth`.

**Note:** The Compose file references a custom `Dockerfile.nginx` for `nginx-rtmp`; if that file is missing, remove the `build` block for `nginx-rtmp` so it uses only the image `tiangolo/nginx-rtmp`.

To run **on the GCP VM**:

1. Install Docker and Docker Compose on the VM (e.g. via startup script or manually).
2. Clone the repo and copy `docker/.env` (and optionally adjust `DB__host` to the Cloud SQL private IP and omit the proxy).
3. Run `docker compose up -d` from `docker/`.

---

## Ingest stream and push to YouTube Live

- **Ingest:** Send RTMP to `rtmp://<host>:1935/live/<stream_key>` (e.g. with OBS).  
  `<host>` is the VM’s public IP (from GCP Console or `gcloud compute instances describe`) or your host if you run Compose locally.

- **YouTube Live:** Configure the Nginx-RTMP application to push to your YouTube RTMP URL (stream key). This may require extending the Nginx config (e.g. `push rtmp://...`) and restarting the container. The current `nginx/nginx.conf` only defines the `live` application; add or adjust the push target as needed for your stream key.

---

## Overlay data

- **Read:** Workers read the Top 10 ranking and PIX alerts from the database (atomic snapshot) every few seconds; if the DB is unreachable, they keep the last known overlay.
- **Write:** The **overlay API** writes donors, alerts, and ranking to the same database. Run it separately (e.g. on the same VM or another host that can reach the DB or the proxy):

  ```bash
  uv run overlay-api
  ```

  Default bind: `0.0.0.0:5001`. Set `API__host` and `API__port` via env if needed.

- **Endpoints:** `POST /donors`, `POST /alerts`, `POST /ranking` (see `src/overlay_api/app.py`). Use these to feed overlay data from your donation/alert backend.

---

## Encoding (YouTube Live)

- CBR 4500 kbps, GOP 2 s, H.264 high profile, level 4.1, tune zerolatency.
- Configured in **`src/config/settings.py`** (EncodingSettings). Override via env (e.g. `ENCODING__cbr_bitrate_k`, `ENCODING__encoder`) or `.env`.

---

## Architecture summary

| Component        | Purpose |
|-----------------|---------|
| **Terraform**   | VPC, firewall (1935, 554), Cloud SQL (PostgreSQL, private IP), Compute Engine VM, IAM. |
| **Nginx-RTMP**  | RTMP ingest on 1935, `live` application. |
| **Worker**      | Demux → overlay (DB) → PTS/DTS → H.264 encode. |
| **Cloud SQL**   | Stores donors, ranking, PIX alerts; read by workers, written by overlay API. |
| **Auth Proxy**  | Allows secure connection to Cloud SQL from Docker or local (no direct public IP on DB). |

---

## Troubleshooting

- **Worker can’t connect to DB:** Ensure `DB__host` and `DB__port` point to the Auth Proxy service (`cloud-sql-auth`) or to the Cloud SQL private IP if not using the proxy. Check that the proxy container is running and `CLOUD_SQL_CONNECTION_NAME` is correct.
- **Terraform apply fails (e.g. API not enabled):** Run the `gcloud services enable` commands from [GCP project setup](#gcp-project-setup).
- **VM has no external IP:** The Compute instance includes `access_config {}`, so it gets an ephemeral external IP. If you use a different Terraform setup without it, you won’t be able to reach RTMP from the internet unless you use a load balancer or another path.
- **Firewall:** Only ports 1935 and 554 are open for ingress; overlay API (5001) and SSH (22) are not in the Terraform firewall. Add rules or use IAP if you need to reach the VM for SSH or the API.

---

## Repo layout

- **`terraform/`** – GCP modules (network, compute, cloud-sql, iam) and prod environment.
- **`docker/`** – Docker Compose, Nginx-RTMP config, Cloud SQL Auth Proxy, Dockerfile for worker.
- **`src/stream_workers/`** – Demux, overlay, PTS/DTS, encode, DB read.
- **`src/overlay_api/`** – Internal API for overlay data writes.
- **`src/config/`** – Centralized Pydantic Settings (DB, encoding, API, worker).
- **`scripts/init_db.py`** – Creates the database schema.
