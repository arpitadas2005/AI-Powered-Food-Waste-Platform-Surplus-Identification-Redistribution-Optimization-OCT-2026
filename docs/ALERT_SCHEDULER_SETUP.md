# Expiry Alert Scheduler & Telemetry Architecture

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 5 — Expiry Tracking, Food Classification and Alert Engine  
**Status**: APPROVED SPECIFICATION  

---

## 1. Operating Modes & Scheduler Telemetry

The platform supports a dual-mode evaluation pattern:

1. **On-Demand & Automated CLI / Cron Mode (Default & Verified)**:
   - Endpoint: `POST /api/v1/alerts/evaluate?dry_run=false`
   - CLI execution: `python -m backend.app.services.expiry_service --evaluate-all`
   - Highly reliable, stateless, and ideal for containerized Cloud Run / Cloud Scheduler cron triggers.
2. **24/7 Distributed Background Worker Queue (Optional Production Mode)**:
   - Requires external task broker: Redis (`REDIS_URL`) or Celery (`CELERY_BROKER_URL`).
   - Requires SMTP delivery service: `SMTP_HOST`, `SMTP_PORT` for email notifications.

### 1.1 Scheduler Telemetry Diagnostics
The endpoint `GET /api/v1/alerts/scheduler/diagnostics` dynamically inspects environment configurations and returns real runtime status without claiming external services are active when they are not:

```json
{
  "success": true,
  "data": {
    "scheduler_mode": "ON_DEMAND_AND_CRON",
    "background_worker_active": false,
    "missing_configurations": [
      "Async Task Broker (REDIS_URL / CELERY_BROKER_URL not configured)",
      "Email Delivery Provider (SMTP_HOST / SENDGRID_API_KEY not configured)",
      "Global Alert Webhook (GLOBAL_ALERT_WEBHOOK_URL not configured)"
    ],
    "recommendation": "Operating in on-demand / cron CLI mode. For automated 24/7 background evaluation, configure an external task scheduler hitting POST /api/v1/alerts/evaluate."
  }
}
```

---

## 2. Production Cron & Cloud Scheduler Setup

### Linux / Crontab (Nightly or Hourly Evaluation)
```bash
# Evaluate expiry alerts every morning at 06:00 UTC
0 6 * * * curl -s -X POST "http://localhost:8000/api/v1/alerts/evaluate?dry_run=false" \
  -H "Authorization: Bearer ${SYSTEM_ADMIN_JWT}" > /dev/null
```

### Google Cloud Scheduler / AWS EventBridge
Configure an hourly HTTPS POST target:
- **Target URL**: `https://api.yourdomain.com/api/v1/alerts/evaluate?dry_run=false`
- **HTTP Method**: `POST`
- **Auth**: OIDC / Service Account Bearer Token
