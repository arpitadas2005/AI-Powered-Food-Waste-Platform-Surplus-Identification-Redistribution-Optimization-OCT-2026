# AI-Powered Food Waste Management Platform — Environment Variables Reference

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: Milestone 4 — Final Deployment Preparation, GitHub Verification & Release Readiness  
**Target Audience**: DevOps Engineers, Site Reliability Engineers, and Cloud Operators  
**Date**: October 2026  

---

## 1. Overview

This document defines all configuration variables used by the backend API and frontend single-page application.

All configuration is managed using **12-Factor App principles** via environment variables or a local `.env` file loaded at application startup via Pydantic Settings (`pydantic-settings`).

---

## 2. Environment Variables Specification

### 2.1 Backend Application & Security Settings

| Variable Name | Type | Default Value | Required in Prod? | Sensitivity | Description & Allowed Values |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `PROJECT_NAME` | `string` | `"AI-Powered Food Waste Management Platform"` | No | Public | Application title displayed in OpenAPI Swagger docs and health probes. |
| `API_V1_STR` | `string` | `"/api/v1"` | No | Internal | Base route prefix for version 1 REST API endpoints. |
| `ENVIRONMENT` | `string` | `"development"` | **YES** | Internal | Operational environment. Allowed values: `development`, `staging`, `production`. |
| `DEBUG` | `boolean` | `False` | No | Internal | Enables detailed debug logs and exception details. **MUST be `False` in production.** |
| `SECRET_KEY` | `string` | *Dev default* | **YES** | **CRITICAL SECRET** | Cryptographic secret key used to sign and verify HMAC-SHA256 JWT tokens. Must be at least 32 characters long. Generate using `secrets.token_hex(32)`. |
| `JWT_ALGORITHM` | `string` | `"HS256"` | No | Internal | Cryptographic hashing algorithm used for JWT token signing. Default: `HS256`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| `integer`| `30` | No | Internal | Duration in minutes before an authenticated access token expires. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `integer`| `7` | No | Internal | Duration in days before a refresh token expires. |

### 2.2 Database Configuration

| Variable Name | Type | Default Value | Required in Prod? | Sensitivity | Description & Allowed Values |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `DATABASE_URL` | `string` | `"sqlite:///./waste_management.db"` | **YES** | **SECRET** | SQLAlchemy connection URI string.<br>• Local SQLite default: `sqlite:///./waste_management.db`<br>• Production PostgreSQL: `postgresql+psycopg://user:password@host:5432/dbname` |

### 2.3 CORS & Network Configuration

| Variable Name | Type | Default Value | Required in Prod? | Sensitivity | Description & Allowed Values |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `BACKEND_CORS_ORIGINS` | `list` / `string` | `["http://localhost:3000","http://127.0.0.1:3000","http://localhost:5173","http://127.0.0.1:5173"]` | **YES** | Internal | Allowed browser client origins. Accepts either a JSON list string `["https://app.example.com"]` or comma-separated list `https://app.example.com,https://portal.example.com`. |

### 2.4 Machine Learning & Storage Settings

| Variable Name | Type | Default Value | Required in Prod? | Sensitivity | Description & Allowed Values |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `MODEL_DIR` | `string` | `"./data/models"` | No | Internal | Filesystem directory containing trained serialized Scikit-Learn `.joblib` model artifacts. |

### 2.5 Frontend Configuration (Vite)

| Variable Name | Type | Default Value | Required in Prod? | Sensitivity | Description & Allowed Values |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `VITE_API_BASE_URL` | `string` | `"/api/v1"` | No | Public | Root URL for the backend API. When frontend is served from the same host/domain via FastAPI or Nginx proxy, keep as relative `"/api/v1"`. If hosted on an external CDN/S3 bucket, set to full URL e.g. `https://api.example.com/api/v1`. |

---

## 3. Cryptographic Secret Generation

For staging and production deployments, generate a cryptographically strong `SECRET_KEY` using Python's standard `secrets` library:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
*Example generated output*:
`8f72a4c8e19b3d02a5e8f4c192d6e3b7a1c8f5d2e4b6a9c3d1f8e2a4b7c9d0e1`

---

## 4. Production Example Configuration

Below is an example `.env` file configured for a secure production environment:

```ini
# Production Environment Configuration
PROJECT_NAME="Food Waste Management Platform"
ENVIRONMENT="production"
DEBUG="False"

# Cryptographic Secret (Replace with unique generated token)
SECRET_KEY="8f72a4c8e19b3d02a5e8f4c192d6e3b7a1c8f5d2e4b6a9c3d1f8e2a4b7c9d0e1"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES="30"
REFRESH_TOKEN_EXPIRE_DAYS="7"

# Database: Production PostgreSQL with SSL mode
DATABASE_URL="postgresql+psycopg://dbuser:StrongPassword987!@postgres.internal.net:5432/waste_prod?sslmode=require"

# CORS: Production domains only
BACKEND_CORS_ORIGINS="https://foodwaste.example.com,https://portal.foodwaste.example.com"

# Machine Learning Artifacts Path
MODEL_DIR="./data/models"

# Frontend API Base URL
VITE_API_BASE_URL="/api/v1"
```

---

## 5. Security & Secret Handling Best Practices

1. **Never Commit Secrets**: Ensure `.env` is listed in `.gitignore` and never committed to version control.
2. **Cloud Secret Managers**: In enterprise cloud environments (AWS, GCP, Azure), inject secrets via **AWS Secrets Manager**, **GCP Secret Manager**, or **Kubernetes Secrets** rather than plaintext disk files.
3. **Log Scrubbing**: The FastAPI application logs do not log passwords, tokens, or JWTs. Standardize log levels to `INFO` or `WARNING` in production.
