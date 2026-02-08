# Cloud SQL Auth Proxy

Run the proxy so workers and overlay_api can connect to Cloud SQL via Private IP.

```bash
# From Terraform output: cloud_sql_connection_name
docker run -p 5432:5432 gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest \
  /cloud-sql-proxy --port=5432 YOUR_CONNECTION_NAME
```

Or use the `cloud-sql-auth` service in docker-compose.yml (set CLOUD_SQL_CONNECTION_NAME in .env).
