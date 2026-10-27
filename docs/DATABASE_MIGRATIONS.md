# AI-Powered Food Waste Management Platform — Database Migrations Guide

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: Milestone 4 — Final Deployment Preparation, GitHub Verification & Release Readiness  
**Target Audience**: Database Administrators, Backend Engineers, and DevOps Operators  
**Date**: October 2026  

---

## 1. Overview

The platform uses **Alembic** in conjunction with **SQLAlchemy 2.0** to manage declarative, version-controlled relational database schema migrations.

All database schema transitions are strictly tracked in `backend/migrations/versions/` and form an unbroken linear progression from initial database creation to the current release head.

---

## 2. Linear Migration History

The migration chain is verified linear and connects as follows:

```
<base>
  │
  ▼
[2d0b94e06dc8] initial_schema
  │            • Creates: tenants, users, inventory_items, inventory_transactions,
  │                       audit_logs, alert_configs, expiry_evaluations,
  │                       pos_integrations, pos_sync_events
  ▼
[671449d6bca3] create_waste_risk_and_smart_reorder_tables
  │            • Creates: waste_risk_assessments, smart_reorders
  │            • Adds: foreign key relationships to inventory_items
  ▼
[975dc57ddcf0] create_ngo_profiles_surplus_claims_and_notifications
  │            • Creates: surplus_listings, ngo_profiles, surplus_claims,
  │                       surplus_notifications
  ▼
[d7ba25360bd9] create_pickup_schedules_table (HEAD)
               • Creates: pickup_schedules
               • Adds: composite indexes for donor/NGO pickup scheduling
```

---

## 3. Operational Migration Commands

Always activate the project virtual environment before running migration commands.

### 3.1 Check Current Database Version
```bash
cd backend
alembic current
```
*Expected Output when synchronized*:
```text
d7ba25360bd9 (head)
```

### 3.2 Inspect Migration History
```bash
cd backend
alembic history --verbose
```

### 3.3 Apply All Pending Migrations (Upgrade to Head)
```bash
cd backend
alembic upgrade head
```
*Production Rule*: Always run `alembic upgrade head` as part of your automated release pipeline before starting application containers.

### 3.4 Roll Back the Most Recent Migration
```bash
cd backend
alembic downgrade -1
```

### 3.5 Generating a New Migration (For Future Schema Changes)
```bash
cd backend
alembic revision --autogenerate -m "describe_your_schema_change_here"
```
*Warning*: Inspect generated migration scripts in `backend/migrations/versions/` before applying to ensure foreign keys, nullability constraints, and index names are properly defined.

---

## 4. Multi-Engine Support: SQLite & PostgreSQL

| Attribute | SQLite (Development / Demo Mode) | PostgreSQL (Production Recommended) |
| :--- | :--- | :--- |
| **Driver** | Built-in Python `sqlite3` | `psycopg` (v3) or `asyncpg` |
| **Connection String** | `sqlite:///./waste_management.db` | `postgresql+psycopg://user:pass@host:5432/dbname` |
| **Concurrency Model** | Database/table locking | Row-level locking (`SELECT ... FOR UPDATE`) |
| **Migration DDL** | Batch table reconstruction for SQLite `ALTER` constraints | Native atomic transactional DDL |
| **Production Fit** | Single-node evaluation, local demos | Clustered, highly available enterprise workloads |

### Applying to Production PostgreSQL:
1. Ensure the PostgreSQL database exists and the user has `CREATE TABLE`, `CREATE INDEX`, and `ALTER TABLE` privileges.
2. Set `DATABASE_URL="postgresql+psycopg://username:password@hostname:5432/database_name"` in `.env`.
3. Execute `alembic upgrade head`.

---

## 5. Indexing & Query Optimization Strategy

The schema incorporates indexes matching query access patterns:

1. **Multi-Tenant Filter Index**: All primary entity queries filter on `tenant_id`. Indexes on `tenant_id` guarantee sub-millisecond filtering and prevent table scans.
2. **Expiry Timeline Index**: `inventory_items(expiry_date)` accelerates FEFO queries and automated alert categorization.
3. **Surplus Marketplace Index**: `surplus_listings(status, expiry_date)` optimizes real-time matching and filtering of active donations.
4. **Logistics Window Index**: `pickup_schedules(pickup_start_time, pickup_end_time, status)` accelerates scheduling conflict detection and calendar views.

---

## 6. Migration Safety & Best Practices

- **Never modify applied migration files**: Once a migration is applied in shared environments, treat it as immutable. Author a new migration for modifications.
- **Always take a backup**: Before running migrations in production, take a database snapshot or backup.
- **Zero data loss migrations**: Never drop tables or columns containing active operational records without a phased migration strategy.
