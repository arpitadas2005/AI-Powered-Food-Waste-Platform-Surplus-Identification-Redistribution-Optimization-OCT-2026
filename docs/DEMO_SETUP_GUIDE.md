# Food Waste Management Platform — Demo Setup & Operator's Guide

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: Milestone 3 — Surplus Identification, NGO Matching & Redistribution Optimization  
**Phase**: Phase 4 — Full-System Integration Testing, Security Validation & Final Demo Readiness  
**Target Audience**: Solutions Architects, Evaluators, Operators, and Demonstrators  
**Date**: October 2026  

---

## 1. Executive Summary

This guide provides step-by-step instructions for running, operating, and demonstrating the complete, end-to-end **AI-Powered Food Waste Management Platform**. The platform integrates:

1. **Inventory Management & Expiry Tracking**: Batch lot tracking, FEFO (First-Expired, First-Out) shelf-life monitoring, and double-entry transaction ledgers.
2. **AI Demand Forecasting & Waste-Risk Scoring**: Scikit-Learn champion models (Random Forest for 1-day ahead, Ridge for 7-day cumulative) evaluating surplus risk and driving smart reorder recommendations.
3. **Surplus Marketplace & NGO Matching**: Multi-factor matching engine with cold-chain safety gates, distance calculation, urgency prioritization, and anti-oversubscription guards.
4. **Claim Management & Logistics Scheduling**: End-to-end claim milestone workflows (`SUBMITTED` $\to$ `APPROVED` $\to$ `SCHEDULED` $\to$ `READY_FOR_COLLECTION` $\to$ `COLLECTED` $\to$ `COMPLETED`), food-safety pickup window validation, and atomic inventory deduction (`DONATION_DISPATCH`).
5. **Business & NGO Dashboards with Sustainability Analytics**: EPA WARM v15 carbon avoidance ($2.5\text{ kg } CO_2e/\text{kg}$), Feeding America meal equivalence ($0.42\text{ kg/meal}$), pure-SVG time-series trend charts, and CWE-1236-protected CSV exports.

---

## 2. System Prerequisites

Ensure the following runtimes and tools are installed on your workstation:

| Component | Minimum Version | Recommended Version | Verification Command |
| :--- | :--- | :--- | :--- |
| **Python** | 3.10+ | 3.11.x | `python --version` |
| **Node.js** | 18.0.0+ | 20.x LTS | `node --version` |
| **npm** | 9.0.0+ | 10.x | `npm --version` |
| **SQLite** | 3.35.0+ | 3.40+ | `sqlite3 --version` |
| **Git** | 2.30+ | 2.40+ | `git --version` |

---

## 3. Environment Configuration

### 3.1 Repository Structure
```
d:\Waste management\
├── backend/
│   ├── alembic.ini
│   ├── app/
│   │   ├── api/v1/         # REST API endpoints (inventory, forecasts, waste_risk, surplus, analytics)
│   │   ├── core/           # Config, database engine, security tokens
│   │   ├── ml/             # ML inference, waste-risk, reorder engine, feature extractors
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic schemas and DTOs
│   │   └── services/       # Business logic (inventory, surplus, matching, analytics)
│   ├── migrations/         # Alembic database migrations (head: d7ba25360bd9)
│   └── tests/              # 168 automated unit, integration, and security tests
├── data/
│   ├── models/             # Trained ML model artifacts (.joblib)
│   ├── processed/          # ML-ready datasets and metadata
│   └── raw/                # Benchmark historical datasets
├── docs/                   # Full architectural, testing, security, and API documentation
├── frontend/               # React 18 + TypeScript + Vite SPA
└── scripts/                # Benchmarking, performance profiling, and batch jobs
```

### 3.2 Backend Configuration (`backend/.env`)
Create or verify `backend/.env` in the project root or backend folder:
```ini
PROJECT_NAME="AI-Powered Food Waste Management Platform"
API_V1_STR="/api/v1"
SECRET_KEY="super-secret-development-key-change-in-production"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Database Connection (SQLite default for local demonstration)
DATABASE_URL="sqlite:///./waste_management.db"

# CORS Configuration
BACKEND_CORS_ORIGINS=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"]

# ML Models Directory
MODEL_DIR="./data/models"
```

### 3.3 Frontend Configuration (`frontend/.env`)
Create or verify `frontend/.env`:
```ini
VITE_API_BASE_URL="http://localhost:8000/api/v1"
```

---

## 4. Installation & First-Time Setup

### Step 1: Backend Environment Setup
From the repository root:
```bash
# 1. Create Python virtual environment (if not already present)
python -m venv .venv

# 2. Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows CMD:
.\.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# 3. Upgrade pip and install backend dependencies
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

### Step 2: Database Migration & Schema Verification
Apply all linear database migrations up to head (`d7ba25360bd9`):
```bash
# Run migrations from within the backend directory
cd backend
alembic upgrade head
cd ..
```
*Verification*: Ensure `waste_management.db` is initialized with all core tables (`tenants`, `users`, `inventory_items`, `inventory_transactions`, `surplus_listings`, `ngo_profiles`, `surplus_claims`, `pickup_schedules`, `surplus_notifications`, `waste_risk_assessments`, `audit_logs`).

### Step 3: Frontend Dependency Installation & Build Verification
```bash
cd frontend
npm install
npm run build
cd ..
```
*Expected Output*: Vite build completes with zero errors, generating static bundles under `frontend/dist/`.

---

## 5. Starting the Application Services

To run a live interactive demonstration, start the backend API server and frontend development server in separate terminal sessions.

### Terminal 1: Backend API Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000 --host 127.0.0.1
```
* The backend will listen at: `http://127.0.0.1:8000`
* Interactive OpenAPI Documentation (Swagger UI): `http://127.0.0.1:8000/docs`
* OpenAPI Redoc: `http://127.0.0.1:8000/redoc`

### Terminal 2: Frontend Single Page Application
```powershell
cd frontend
npm run dev -- --host
```
* The frontend UI will be available at: `http://localhost:5173` (or `http://localhost:3000` if configured).

---

## 6. Service Health Check & Verification Probes

Before beginning a demonstration, verify that all backend subsystems and ML models are healthy:

| Check | Endpoint | Method | Expected Status | Purpose |
| :--- | :--- | :---: | :---: | :--- |
| **API Liveness** | `/health` | `GET` | `200 OK` | Verifies that the FastAPI application is alive and accepting connections. |
| **Database Readiness** | `/health/ready` | `GET` | `200 OK` | Pings the database engine to verify read/write connectivity. |
| **ML Inference Health** | `/api/v1/forecasts/health` | `GET` | `200 OK` | Verifies that `champion_1d_forecaster.joblib` and `champion_7d_forecaster.joblib` are loaded. |

#### Example Health Check Response (`/health/ready`):
```json
{
  "status": "ready",
  "database": "connected",
  "timestamp": "2026-10-27T17:30:00Z"
}
```

#### Example ML Health Check Response (`/api/v1/forecasts/health`):
```json
{
  "status": "healthy",
  "models": {
    "model_1d_loaded": true,
    "model_7d_loaded": true
  },
  "champion_1d": "RandomForest_1d",
  "champion_7d": "Ridge_7d"
}
```

---

## 7. Demo Accounts & Personas

The platform enforces strict role-based access control (RBAC) and tenant isolation. For testing and demonstration, use these representative roles and accounts:

| Persona | Organization Name | Tenant Type | Role | Default Email | Use Case / Permissions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Donor Business (Primary)** | Green Grocer Downtown | Commercial Retailer | `STORE_MANAGER` / `BUSINESS_OWNER` | `green.grocer@example.com` | Manages fresh inventory, views waste-risk alerts, publishes surplus listings, approves claims, confirms pickup handovers. |
| **Donor Business (Secondary)** | Artisan Bakery Uptown | Commercial Bakery | `BUSINESS_OWNER` | `artisan.bakery@example.com` | Publishes baked surplus lots; demonstrates multi-tenant isolation against Green Grocer Downtown. |
| **Recipient NGO** | Community Food Bank | Verified Non-Profit | `RECIPIENT_NGO` | `foodbank@example.com` | Browses matched surplus listings, submits claims, schedules volunteer collection windows, views meals served. |
| **System Administrator** | Platform Operations | Internal Admin | `SYSTEM_ADMIN` | `admin@example.com` | Global oversight, audit log review, tenant provisioning, cross-organization governance. |

---

## 8. Guided Demonstration Script (Step-by-Step)

Follow this 5-stage workflow to showcase the full platform capabilities to evaluators:

```
[ Stage 1: Inventory & Expiry ] ──> [ Stage 2: AI Forecasting & Risk ] ──> [ Stage 3: Surplus Publishing & Matching ]
                                                                                              │
                                                                                              ▼
[ Stage 5: Dashboards & Sustainability ] <── [ Stage 4: Claim, Pickup & Stock Deduction ] <──┘
```

### Stage 1: Inventory Management & FEFO Expiry Tracking
1. Open the UI at `http://localhost:5173` and navigate to the **Inventory** view.
2. Observe active inventory lots categorized by perishability:
   - Items with $\le 3$ days to expiry are highlighted with warning badges.
   - Batch numbers, lot creation dates, and shelf-life expiration dates are displayed.
3. Add a new perishable batch (e.g., Organic Whole Milk, 50 units, expiring in 3 days) or inspect existing dairy/produce lots.
4. Note that every inventory change automatically generates an immutable audit record in the double-entry transaction ledger (`inventory_transactions`).

### Stage 2: AI Forecasting & Waste-Risk Scoring
1. Navigate to the **Forecasting & Waste Risk** tab.
2. Select a perishable SKU (e.g., *Organic Whole Milk*).
3. The platform invokes the trained `RandomForest` model to predict 1-day ahead demand and the `Ridge` model for 7-day cumulative demand.
4. Review the automated **Waste-Risk Assessment**:
   - Compares current stock vs. expected demand over the remaining shelf-life.
   - Computes Expected Surplus (kg) and Value-at-Risk ($).
   - Generates an explainable risk tier: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
   - Recommends proactive action: e.g., *"Publish to Surplus Marketplace immediately"*.
5. Review the **Smart Reorder Recommendation**:
   - Dynamically calculates reorder point based on lead-time demand + safety stock ($Z = 1.65$).
   - Demonstrates the **Expiry Risk Suppression Guard**: If an item is classified as `HIGH` or `CRITICAL` waste risk, replenishment orders are automatically suppressed to avoid compounding waste.

### Stage 3: Surplus Food Listing & Explainable NGO Matching
1. From the high-risk alert or the **Surplus Listings** view, create a new surplus donation:
   - Item: *Organic Whole Milk*
   - Available Quantity: *40 kg*
   - Perishability: `DAIRY` (requires cold storage)
   - Expiration Date: *3 days from today*
2. Publish the listing. The platform verifies:
   - Anti-oversubscription gate: Total surplus allocations cannot exceed on-hand inventory.
   - Food-safety gate: Shelf-life must be valid and non-expired.
3. Switch to the **NGO Matching** view.
4. The Matching Engine evaluates registered non-profits using an explainable multi-factor scoring formula:
   - **Cold-Chain Gate**: Organizations lacking cold storage for dairy products are safely filtered out.
   - **Proximity Score**: Computed using true Haversine distance between donor and NGO coordinates.
   - **Category Match Score**: NGO accepted food categories vs. listing category.
   - **Urgency Bonus**: Elevated priority for items with imminent expiry.
   - **Verification Bonus**: Verified 501(c)(3) or equivalent accredited NGOs receive priority.
5. Inspect the score breakdown: Evaluators can see exactly why each NGO was ranked in that position.

### Stage 4: Claim Management, Pickup Scheduling & Stock Handover
1. Switch perspective to the **Recipient NGO** (`foodbank@example.com`).
2. Submit a Claim for 30 kg of the available 40 kg.
   - The listing transitions its reserved quantity: 30 kg `RESERVED`, 10 kg remaining `AVAILABLE`.
3. Switch back to the **Donor Business** (`green.grocer@example.com`).
4. In the Claim Review panel, review and **Approve** the claim (`APPROVED`).
5. In the Pickup Scheduling modal, schedule a collection window:
   - The system validates that `pickup_end_time <= listing.expiry_date` (food safety gate).
   - Status advances to `SCHEDULED`.
6. When the volunteer arrives, donor clicks **Mark Ready for Collection** (`READY_FOR_COLLECTION`).
7. Once loaded into the vehicle, NGO or donor clicks **Confirm Collection** (`COLLECTED`).
8. Finalize the handover by clicking **Complete Transfer** (`COMPLETED`):
   - The platform executes an atomic stock deduction (`DONATION_DISPATCH`) on the donor's physical inventory ledger.
   - Available and reserved quantities are permanently reconciled.
   - The operation is protected by an idempotency guard: duplicate calls cannot trigger double deduction.

### Stage 5: Business/NGO Dashboards & Sustainability Analytics
1. Navigate to the **Dashboards & Analytics** view.
2. **Business Impact View**:
   - Executive metrics: Rescued stock (kg), inventory valuation protected, active surplus, and pending transfers.
3. **NGO Recipient View**:
   - Food mass received (kg), nutritional community meals served ($0.42\text{ kg/meal}$), and logistical schedule tracker.
4. **Sustainability & ESG Impact Engine**:
   - Carbon avoidance calculated using EPA WARM v15 standards:
     $$\text{Emissions Avoided (kg } CO_2e) = \text{Mass Rescued (kg)} \times 2.5\text{ kg } CO_2e/\text{kg}$$
   - Tree absorption equivalence: $\approx 21.77\text{ kg } CO_2/\text{tree-year}$.
   - Passenger vehicle miles avoided: $\approx 0.393\text{ kg } CO_2e/\text{mile}$.
5. **Interactive Data Visualizations**:
   - Dynamic Pure-SVG trend line charts displaying daily/monthly rescued kilograms.
   - Category distribution bar charts showing rescue mass across produce, dairy, bakery, and prepared foods.
6. **Secure CSV Export**:
   - Click **Export Sustainability Audit Report (.csv)**.
   - Inspect the downloaded file: Cells are protected against Spreadsheet Formula Injection (CWE-1236) by automatically quoting formulas starting with `=`, `+`, `-`, `@`.

---

## 9. Performance & Latency Benchmarks

Measured on standard test workstations via automated benchmarking tools (`scripts/measure_performance.py`):

| Endpoint / Operation | Sample Count | Mean Latency | Median Latency | p95 Latency | SLA Threshold | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `GET /health` (Liveness) | 100 calls | **4.19 ms** | 3.92 ms | 5.65 ms | $< 50\text{ ms}$ | **EXCEEDS SLA** |
| `GET /health/ready` (DB Ping) | 100 calls | **5.35 ms** | 5.12 ms | 7.48 ms | $< 100\text{ ms}$ | **EXCEEDS SLA** |
| `GET /api/v1/inventory` (Auth) | 50 calls | **5.94 ms** | 5.81 ms | 7.62 ms | $< 150\text{ ms}$ | **EXCEEDS SLA** |
| **ML Inference (7-day forecast)** | 100 calls | **0.03 ms** | 0.03 ms | 0.04 ms | $< 25\text{ ms}$ | **EXCEEDS SLA** |
| `GET /api/v1/analytics/business` | 50 calls | **6.11 ms** | 5.95 ms | 7.24 ms | $< 200\text{ ms}$ | **EXCEEDS SLA** |
| `GET /api/v1/analytics/sustainability`| 50 calls | **5.65 ms** | 5.50 ms | 6.82 ms | $< 200\text{ ms}$ | **EXCEEDS SLA** |

---

## 10. Synthetic Data & Testing Disclosure

> [!NOTE]
> **Data Provenance Disclosure**:
> In accordance with ethical AI evaluation and data transparency standards, all customer transactional histories, inventory counts, store locations, and non-profit organization details utilized in demonstration mode and benchmark datasets are **synthetically generated**. 
> - Time-series trends reflect realistic retail grocery distributions (smooth, seasonal, and intermittent demand patterns).
> - Environmental impact formulas are grounded in published scientific standards (EPA WARM v15 and Feeding America).
> - No real customer, store, or proprietary enterprise data has been collected or exposed.
