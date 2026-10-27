# AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization

[![Test Suite](https://img.shields.io/badge/pytest-168%20passed%20(100%25)-brightgreen.svg)](backend/tests/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python)](https://python.org)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6.svg?logo=typescript)](https://www.typescriptlang.org)
[![Alembic](https://img.shields.io/badge/Alembic-head%20(d7ba25360bd9)-orange.svg)](backend/migrations/)
[![Security Audit](https://img.shields.io/badge/Security-CWE--1236%20%26%20IDOR%20Protected-success.svg)](docs/SECURITY_VALIDATION_REPORT.md)

---

## 1. Project Overview

The **AI-Powered Food Waste Management Platform** is an enterprise-grade full-stack system designed to eliminate retail grocery and food business surplus waste before spoilage occurs.

By combining real-time inventory lot tracking (FEFO) with machine learning time-series demand forecasting, the platform proactively identifies overstock risk, alerts managers, suppresses wasteful replenishments, and automatically publishes expiring surplus to an explainable NGO redistribution marketplace for volunteer rescue and community meal donation.

### Key Value Propositions
- **Proactive Waste Prevention**: Predicts consumer demand over the remaining product shelf life using multi-horizon machine learning models (Random Forest and Ridge).
- **Explainable Surplus Matching**: Ranks verified non-profits based on cold-chain storage safety, true Haversine distance, accepted food categories, and expiration urgency.
- **Auditable Logistics & Stock Reconciliation**: Database-backed pickup scheduling within food-safety windows with atomic physical inventory deduction (`DONATION_DISPATCH`).
- **Verified Environmental & ESG Reporting**: Quantifies rescued kilograms, community meals served, avoided carbon emissions (EPA WARM v15), and tree/vehicle equivalents with CWE-1236-protected CSV audit exports.

---

## 2. Technology Stack

| Layer | Technologies | Key Capabilities |
| :--- | :--- | :--- |
| **Backend API** | Python 3.11+, FastAPI, Pydantic v2 | Asynchronous REST endpoints, strict request validation, uniform error handlers, request ID tracing (`X-Request-ID`). |
| **Database & ORM** | SQLAlchemy 2.0, Alembic, SQLite / PostgreSQL | Multi-tenant relational schema, double-entry inventory ledger, declarative migrations, composite indexing, row-level concurrency. |
| **Security & Auth** | Passlib (Bcrypt), Python-Jose (JWT) | Stateless JWT bearer tokens, bcrypt password hashing, RBAC (`BUSINESS_OWNER`, `STORE_MANAGER`, `RECIPIENT_NGO`), IDOR/BOLA horizontal isolation. |
| **Machine Learning** | Scikit-Learn, Pandas, NumPy, Joblib | Zero-leakage temporal feature engineering, multi-horizon demand forecasting (1-day & 7-day), statistical reorder safety stock ($Z=1.65$). |
| **Frontend SPA** | React 18, TypeScript, Vite, Lucide Icons | Responsive multi-role portal, interactive pickup scheduling modals, logistics milestone trackers, pure-SVG trend visualizations, browser CSV downloads. |

---

## 3. Architecture & Data Flow

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND CLIENT (React 18)                             │
│   [Store Manager View]        [NGO Recipient Marketplace]        [ESG Impact Portal]   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ REST Calls via /api/v1 (JWT Auth)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               FASTAPI BACKEND APPLICATION                              │
│                                                                                        │
│   ┌────────────────────┐   ┌─────────────────────┐   ┌─────────────────────────────┐   │
│   │  Inventory Engine  │   │  ML Forecast Engine │   │   Surplus & NGO Engine      │   │
│   │  • FEFO Expiry     │   │  • 1d Random Forest │   │   • Anti-oversubscription   │   │
│   │  • Lot Tracking    │   │  • 7d Ridge Model   │   │   • Cold-Chain Safety Gate  │   │
│   │  • Double Ledger   │   │  • Waste-Risk Tiers │   │   • Explainable Matching    │   │
│   └─────────┬──────────┘   └──────────┬──────────┘   └──────────────┬──────────────┘   │
│             │                         │                             │                  │
│             ▼                         ▼                             ▼                  │
│   ┌────────────────────────────────────────────────────────────────────────────┐       │
│   │                     Logistics & Impact Analytics Engine                    │       │
│   │    • Pickup Scheduling & Handover      • EPA WARM v15 Carbon Avoidance     │       │
│   │    • Atomic Stock Deduction            • Feeding America Meals Equivalence │       │
│   └─────────────────────────────────────┬──────────────────────────────────────┘       │
└─────────────────────────────────────────┼──────────────────────────────────────────────┘
                                          │ SQLAlchemy ORM
                                          ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              RELATIONAL DATABASE STORAGE                               │
│     tenants │ users │ inventory_items │ inventory_transactions │ surplus_listings      │
│     ngo_profiles │ surplus_claims │ pickup_schedules │ waste_risk_assessments          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Feature Verification Status

All 13 core platform modules have been verified across automated unit, integration, and security test suites (**168 / 168 tests passing, 100%**):

| Module | Verification Scope | Status |
| :--- | :--- | :---: |
| **Inventory Management** | Batch lots, SKU tracking, manual stock adjustments, double-entry audit ledger | **VERIFIED** |
| **Expiry Alerts** | FEFO shelf-life classification ($\le 3$ days, $\le 7$ days), tenant threshold configs | **VERIFIED** |
| **CSV Data Ingestion** | Bulk inventory upload, header mapping, unit normalization (`lbs` $\to$ `kg`), validation | **VERIFIED** |
| **AI Demand Forecasting** | 1-day ahead (15.05% Test WAPE) & 7-day cumulative (7.03% Test WAPE), fallback baseline | **VERIFIED** |
| **Waste-Risk Scoring** | Expected surplus (kg), Value-at-Risk ($), explainable tiers (`LOW` to `CRITICAL`) | **VERIFIED** |
| **Smart Replenishment** | Reorder points with safety stock ($Z=1.65$), Expiry Risk Suppression Guard | **VERIFIED** |
| **Surplus Food Listings** | Multi-state lifecycle, storage condition tags, food-safety gates, anti-oversubscription | **VERIFIED** |
| **NGO Matching Engine** | Cold-chain safety gate, Haversine proximity, accepted categories, verification bonus | **VERIFIED** |
| **Claims & Logistics** | Scheduling windows, milestone progression, atomic stock deduction (`DONATION_DISPATCH`) | **VERIFIED** |
| **In-App Notifications** | Event-driven alerts for matches, claims, scheduling, rescheduling, and deliveries | **VERIFIED** |
| **Business Dashboard** | Commercial stock, expiring lots, ML high-risk alerts, active surplus, pending pickups | **VERIFIED** |
| **NGO Recipient Portal** | Matched eligible donations, claim allocations, logistics windows, meals served | **VERIFIED** |
| **Sustainability Analytics** | EPA WARM v15 emissions avoidance, Feeding America meals, pure-SVG trend charts, CSV export | **VERIFIED** |

---

## 5. Quick Start & Local Setup

### 5.1 System Prerequisites
- **Python**: 3.10+ (Recommended: 3.11.x)
- **Node.js**: 18.0.0+ (Recommended: 20.x LTS)
- **npm**: 9.0.0+
- **Git**: 2.30+

### 5.2 Backend Installation & Database Setup
```bash
# 1. Clone repository and navigate to root
cd "d:\Waste management"

# 2. Set up Python virtual environment
python -m venv .venv
# Activate on Windows:
.\.venv\Scripts\Activate.ps1
# Activate on Linux/macOS:
source .venv/bin/activate

# 3. Install backend dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt

# 4. Initialize environment configuration
copy .env.example .env

# 5. Apply linear database migrations to head
cd backend
alembic upgrade head
cd ..

# 6. Start the FastAPI development server
python -m uvicorn backend.app.main:app --reload --port 8000 --host 127.0.0.1
```
* Backend API listens at: `http://127.0.0.1:8000`
* Interactive OpenAPI Swagger Documentation: `http://127.0.0.1:8000/docs`
* OpenAPI Redoc: `http://127.0.0.1:8000/redoc`

### 5.3 Frontend Installation & Startup
In a separate terminal window:
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start Vite development server
npm run dev
```
* Frontend application opens at: `http://localhost:5173` (or `http://localhost:3000`)

---

## 6. Service Health Check Probes

Verify system health before demonstrations or deployment:

```bash
# API Liveness Probe
curl http://127.0.0.1:8000/health
# Response: {"status": "ok", "project": "AI-Powered Food Waste Management Platform"}

# Database Connectivity Probe
curl http://127.0.0.1:8000/health/ready
# Response: {"status": "ready", "database": "connected"}

# Machine Learning Inference Health Probe
curl http://127.0.0.1:8000/api/v1/forecasts/health
# Response: {"status": "healthy", "models": {"model_1d_loaded": true, "model_7d_loaded": true}}
```

---

## 7. Testing & Quality Assurance

The test suite covers end-to-end user journeys, ML pipelines, database concurrency, and security attack simulations:

```bash
# Execute full backend automated test suite (168 tests)
pytest -q

# Execute frontend TypeScript check and production build
cd frontend
npm run build
```

### Performance & Latency Benchmarks
Measured via `scripts/measure_performance.py`:
- `GET /health` (Liveness): **4.19 ms** mean
- `GET /health/ready` (Database ping): **5.35 ms** mean
- `GET /api/v1/inventory` (Auth): **5.94 ms** mean
- `ML Inference (7-Day Forecast)`: **0.03 ms** mean
- `GET /api/v1/analytics/sustainability`: **5.65 ms** mean

---

## 8. Security Architecture

1. **Authentication & Authorization**: Stateless JWT bearer tokens signed with HMAC-SHA256. Passwords hashed using bcrypt ($>12$ rounds).
2. **Broken Object-Level Authorization (BOLA/IDOR)**: Multi-tenant queries strictly scope `tenant_id == current_user.tenant_id`. Cross-tenant requests return `404 Not Found` without disclosing record existence.
3. **Formula Injection Defense (CWE-1236)**: Dynamic CSV export sanitizes cells starting with `=`, `+`, `-`, `@`, `\t`, `\r` by prepending a single quote, neutralizing malicious macro execution in spreadsheet viewers.
4. **SQL Injection Defense**: Strict usage of SQLAlchemy ORM parameterized statements across all queries.
5. **Secret Redaction**: Response schemas filter out credential attributes (`hashed_password`).

---

## 9. Documentation Index

Detailed architectural specifications, verification reports, and guides are located in [`docs/`](docs/):

- [`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md): Comprehensive feature readiness matrix and release sign-off.
- [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md): Docker, Systemd, Nginx, and cloud deployment procedures.
- [`docs/ENVIRONMENT_VARIABLES.md`](docs/ENVIRONMENT_VARIABLES.md): Full reference of application configuration variables.
- [`docs/DATABASE_MIGRATIONS.md`](docs/DATABASE_MIGRATIONS.md): Alembic migration chain, multi-engine support, and indexing.
- [`docs/DEMO_SETUP_GUIDE.md`](docs/DEMO_SETUP_GUIDE.md): Step-by-step operator guide for live demonstrations.
- [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md): Technical considerations and defect resolutions.
- [`docs/INTEGRATION_TEST_REPORT.md`](docs/INTEGRATION_TEST_REPORT.md): Full-system end-to-end integration test results.
- [`docs/SECURITY_VALIDATION_REPORT.md`](docs/SECURITY_VALIDATION_REPORT.md): Penetration testing and security controls audit.
- [`docs/ML_VALIDATION_REPORT.md`](docs/ML_VALIDATION_REPORT.md): ML model training, zero-leakage perturbation tests, and benchmarks.

---

## 10. Data Provenance & Ethics Disclosure

All transaction logs, store locations, and non-profit organization details utilized in demonstration mode and benchmark evaluations are **synthetically generated** using realistic retail grocery distributions. No proprietary retail transactions or private donor data are stored in version control.
