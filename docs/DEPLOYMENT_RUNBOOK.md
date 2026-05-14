# SignalForge Deployment Runbook  
**Phase 6V — Production Deployment Drill**

---

## 1. Pre-Deployment Checklist

| Item | Command / Action |
|------|-----------------|
| All tests pass locally | `python -m pytest tests/ -q` |
| Docker images build cleanly | `docker compose build` |
| `.env.production` configured | See §2 |
| MongoDB URI is reachable | `docker compose exec api python -c "from pymongo import MongoClient; MongoClient(os.environ['MONGO_URI']).admin.command('ping')"` |
| Redis is reachable | `docker compose exec api redis-cli -u $REDIS_URL ping` |
| `SIGNALFORGE_AUTH_ENABLED=true` set in prod env | Verify in `.env.production` |
| `SIGNALFORGE_RATE_LIMIT_ENABLED=true` set in prod env | Verify in `.env.production` |

---

## 2. Environment Configuration

Copy and populate `.env.production`:

```bash
cp .env.production.template .env.production  # if template exists
# -- or --
cat > .env.production << 'EOF'
MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/signalforge?retryWrites=true
REDIS_URL=redis://<host>:6379/0
JWT_SECRET=<generate: python -c "import secrets; print(secrets.token_hex(32))">
SIGNALFORGE_AUTH_ENABLED=true
SIGNALFORGE_RATE_LIMIT_ENABLED=true
SIGNALFORGE_ENVIRONMENT=production
EOF
```

**Never commit `.env.production` to source control.**

---

## 3. Build & Deploy

```bash
# 1. Build images
docker compose -f docker-compose.prod.yml build

# 2. Run pre-flight smoke (against staging or local)
docker compose -f docker-compose.prod.yml run --rm api \
  pytest tests/ -q --tb=short 2>&1 | tail -20

# 3. Bring up services
docker compose -f docker-compose.prod.yml up -d

# 4. Verify health
curl http://localhost:8000/health
curl http://localhost:8000/system/pilot-readiness
```

---

## 4. Auth-On Validation

When `SIGNALFORGE_AUTH_ENABLED=true`:

1. Request a token:
   ```bash
   curl -X POST http://localhost:8000/auth/token \
     -H "Content-Type: application/json" \
     -d '{"api_key": "<your-key>", "workspace_slug": "<slug>"}'
   ```

2. Use the token:
   ```bash
   curl http://localhost:8000/system/pilot-readiness \
     -H "Authorization: Bearer <token>"
   ```

3. Verify a request without a token returns `401`.

---

## 5. Rate-Limit Validation

When `SIGNALFORGE_RATE_LIMIT_ENABLED=true`, the API enforces 60 requests/min per key:

```bash
# Send 65 requests; the 61st+ should return 429
for i in $(seq 1 65); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
  echo "$i: $STATUS"
done
```

---

## 6. Backup Drill

```bash
# Create a full backup
python scripts/backup_restore.py backup --out backup_$(date +%Y%m%d).json

# Verify the backup file
python - << 'EOF'
import json, gzip, base64
b = json.load(open("backup_*.json"))
raw = gzip.decompress(base64.b64decode(b["payload"]))
snap = json.loads(raw)
print(f"Version: {snap['version']}, Collections: {list(snap['collections'])}")
EOF

# Dry-run restore (validates payload, no writes)
python scripts/backup_restore.py restore --file backup_*.json --dry-run
```

---

## 7. Worker & Orchestration Recovery Drill

```bash
# Check current status
python scripts/backup_restore.py status

# If orphaned_task_risk is true, trigger recovery:
curl -X POST http://localhost:8000/workers/recover-orphaned \
  -H "Authorization: Bearer <token>"

# Re-check
python scripts/backup_restore.py status
```

---

## 8. Rollback Procedure

1. Scale down the new deployment:
   ```bash
   docker compose -f docker-compose.prod.yml down
   ```

2. Restore from the pre-deployment backup:
   ```bash
   python scripts/backup_restore.py restore --file pre_deploy_backup.json
   ```

3. Bring up the previous image:
   ```bash
   git checkout <previous-tag>
   docker compose -f docker-compose.prod.yml build
   docker compose -f docker-compose.prod.yml up -d
   ```

---

## 9. Monitoring Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Basic liveness check |
| `GET /health/detailed` | DB + worker connectivity |
| `GET /system/pilot-readiness` | Weighted readiness score (0–100) |
| `GET /system/recovery-status` | Stuck orchestrations + worker health |
| `GET /system/telemetry` | Request counts, latency, error rates |
| `GET /system/indexes` | Index health across all collections |
| `GET /workers/health` | Worker registry status |
| `GET /system/audit-log` | Last N audit events |

---

## 10. Go / No-Go Decision Gate

Run the pilot readiness check. A score ≥ 80 with `ready: true` is required before live traffic:

```bash
curl http://localhost:8000/system/pilot-readiness | python -m json.tool
```

Expected response shape:
```json
{
  "ready": true,
  "score": 90,
  "max_score": 100,
  "checks": {
    "mongodb_reachable": true,
    "indexes_created": true,
    "tracing_active": true,
    "metrics_operational": true,
    "audit_log_operational": true,
    "worker_system_operational": true,
    "orchestration_recovery_operational": true,
    "auth_configurable": true,
    "rate_limit_configurable": true
  }
}
```
