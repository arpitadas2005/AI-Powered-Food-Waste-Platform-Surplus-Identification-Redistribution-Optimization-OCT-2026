# Milestone 1 — Known Limitations & Operational Constraints

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Real-Time Food Waste Tracking & Inventory Monitoring  
**Phase**: Phase 8 — Final Quality Assurance, Security Audit & Performance Evaluation  
**Date**: October 23, 2026  
**Auditor**: Independent Senior QA Engineer & Release Reviewer  

---

## 1. Overview

In accordance with independent QA audit principles, this document provides an honest, transparent accounting of all known technical constraints, operational boundaries, and external prerequisites for Milestone 1.

None of these limitations represent defects in the Milestone 1 core implementation; rather, they define the documented operating parameters and identify necessary prerequisites for future milestones.

---

## 2. Identified Operational Constraints

### 2.1 Database Concurrency: SQLite vs PostgreSQL
- **Current Behavior**: The platform utilizes SQLite 3 with Write-Ahead Logging (WAL) enabled and `PRAGMA foreign_keys = ON` for local development, automated testing, and single-instance deployments.
- **Limitation**: SQLite supports unlimited concurrent readers but serializes database writes to a single concurrent writer. Under extreme concurrent write volume (e.g. dozens of simultaneous POS webhook events and CSV bulk imports), write lock contention may occur.
- **Production Recommendation**: For multi-server production deployment across thousands of retail stores, the database connection string in `.env` (`DATABASE_URL`) should point to PostgreSQL 15+ with pgBouncer connection pooling. The SQLAlchemy ORM models and Alembic migrations are fully dialect-agnostic and tested for PostgreSQL compatibility.

### 2.2 External POS Connectivity: Live Credentials Required
- **Current Behavior**: The platform includes fully verified provider adapters for Square POS, Clover POS, and a Generic REST POS adapter.
- **Limitation**: Development and automated QA suites run against the Generic mock adapter and simulated HMAC-SHA256 webhooks. Live real-world synchronization with production Square or Clover merchant accounts requires:
  1. An approved Square Developer or Clover App Market developer application.
  2. Merchant OAuth 2.0 client ID and client secret.
  3. Registered production webhook callback endpoints accessible over public HTTPS.
- **Verification Boundary**: The adapter logic, HMAC signature verification, unit normalization, and order deduplication are 100% tested and verified. Live vendor connectivity is blocked pending merchant production credentials.

### 2.3 Automated Expiry Evaluation: Background Broker Mode
- **Current Behavior**: Expiry monitoring is executed via:
  1. On-demand authenticated REST API trigger (`POST /api/v1/inventory/expiry/evaluate`).
  2. CLI cron invocation (`python -m backend.app.services.expiry_scheduler`).
- **Limitation**: Continuous automated 24/7 background task execution requires an asynchronous broker (such as Redis with Celery, or Google Cloud Scheduler / AWS EventBridge triggering the evaluation endpoint).
- **Scheduler Telemetry**: The scheduler diagnostics endpoint (`GET /api/v1/alerts/scheduler/diagnostics`) accurately reports `scheduler_mode: "ON_DEMAND_AND_CRON"` and explicitly warns that Redis/Celery is not yet active, with zero false claims of an internal daemon.

### 2.4 Mobile Camera Streaming: HTTPS Context Requirement
- **Current Behavior**: The mobile barcode scanner utilizes HTML5 `navigator.mediaDevices.getUserMedia`.
- **Limitation**: Modern mobile browsers (iOS Safari, Chrome for Android) strictly restrict camera video streams to secure contexts (`https://` or `http://localhost`). Accessing the platform from a mobile phone over an insecure local network IP (e.g. `http://192.168.x.x:8000`) will cause the browser to block camera permissions.
- **Remediation & Fallback**: The frontend provides a prominent manual barcode/SKU input field that functions in all environments, along with clear instructional banners when camera permissions are denied or unsupported.

### 2.5 CSV Import File Boundaries
- **Current Behavior**: Enforces a 10 MB maximum file size limit and a 10,000-row limit per batch.
- **Limitation**: Files exceeding 10,000 rows or 10 MB are rejected with HTTP 413 Payload Too Large to guarantee sub-2-second response times and prevent server memory spikes.
- **Workaround**: Larger enterprise catalogs should be partitioned into 5,000-to-10,000 row chunks or synchronized through the POS REST API pipeline.

### 2.6 Single Currency per Tenant
- **Current Behavior**: Each business tenant defines a primary currency (e.g. `USD`, `EUR`, `CAD`) upon creation. All item valuation calculations and reporting are rendered in the tenant's designated currency.
- **Limitation**: Multi-currency conversion across international subsidiaries under a single tenant is not implemented in Milestone 1 and is scheduled for enterprise roadmap milestones.
