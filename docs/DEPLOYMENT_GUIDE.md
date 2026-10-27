# AI-Powered Food Waste Management Platform — Production Deployment Guide

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: Milestone 4 — Final Deployment Preparation, GitHub Verification & Release Readiness  
**Target Audience**: DevOps Engineers, Site Reliability Engineers, and Cloud Architects  
**Date**: October 2026  

---

## 1. Overview & Architecture

The **AI-Powered Food Waste Management Platform** is architected as a modern, decoupled cloud application:

- **Backend**: Python 3.11+ / FastAPI asynchronous REST API with SQLAlchemy 2.0 ORM and Pydantic validation.
- **Frontend**: React 18 / TypeScript single-page application bundled with Vite.
- **AI/ML Layer**: Embedded Scikit-Learn inference engine (`data/models/champion_1d_forecaster.joblib` and `champion_7d_forecaster.joblib`) executing in-process ($< 0.1\text{ ms}$ latency).
- **Relational Database**: PostgreSQL 15+ (Production) or SQLite 3.35+ (Evaluation/Local Staging).
- **Reverse Proxy**: Nginx / Cloudflare terminating TLS/HTTPS and proxying API traffic.

```
                  ┌────────────────────────────────────────┐
                  │           Internet / Clients           │
                  └───────────────────┬────────────────────┘
                                      │ HTTPS (Port 443)
                                      ▼
                  ┌────────────────────────────────────────┐
                  │      Edge Proxy / Nginx Gateway        │
                  │   (TLS Termination, Rate Limiting)     │
                  └───────────┬────────────────┬───────────┘
                              │                │
            /api/* or Dynamic │                │ /assets/* or Static
                              ▼                ▼
                  ┌──────────────────────┐ ┌───────────────┐
                  │    FastAPI Server    │ │  Vite Static  │
                  │   (Uvicorn Worker)   │ │  Distribution │
                  └───────────┬──────────┘ └───────────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
   ┌───────────────────────┐     ┌───────────────────────┐
   │  PostgreSQL Database  │     │   ML Model Artifacts  │
   │  (Relational Storage) │     │     (data/models/)    │
   └───────────────────────┘     └───────────────────────┘
```

---

## 2. Pre-Deployment Checklist

Before deploying to staging or production, verify that:

- [ ] All 168 automated tests pass (`pytest -q`).
- [ ] Frontend builds with zero TypeScript errors (`npm run build`).
- [ ] Target PostgreSQL database instance is provisioned and reachable.
- [ ] A cryptographically secure `SECRET_KEY` ($\ge 32$ hex chars) is generated.
- [ ] `ENVIRONMENT="production"` and `DEBUG="False"` are set in production environment variables.
- [ ] `BACKEND_CORS_ORIGINS` is restricted to authorized production client domains.
- [ ] Model artifacts are located in `data/models/` or mounted via persistent volume.
- [ ] Database migration head (`d7ba25360bd9`) is ready to apply.

---

## 3. Containerized Deployment (Docker & Docker Compose)

### 3.1 Backend `Dockerfile`
A production multi-stage Dockerfile for the FastAPI backend:

```dockerfile
# Build Stage: Python dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Stage
FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy installed wheels from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source and model binaries
COPY backend/ ./backend/
COPY data/models/ ./data/models/

# Expose port and configure health probe
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn with standard production settings
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 3.2 Frontend `Dockerfile` (Static Nginx Web Server)
```dockerfile
# Build Stage
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Runtime Stage
FROM nginx:alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 3.3 `docker-compose.yml` (Complete Production Stack)
```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    container_name: foodwaste_postgres
    restart: always
    environment:
      POSTGRES_DB: food_waste_prod
      POSTGRES_USER: waste_admin
      POSTGRES_PASSWORD: ${DB_PASSWORD:-StrongSecurePassword123!}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U waste_admin -d food_waste_prod"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: foodwaste_backend
    restart: always
    depends_on:
      db:
        condition: service_healthy
    environment:
      PROJECT_NAME: "AI-Powered Food Waste Management Platform"
      ENVIRONMENT: "production"
      DEBUG: "False"
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: "postgresql+psycopg://waste_admin:${DB_PASSWORD:-StrongSecurePassword123!}@db:5432/food_waste_prod"
      BACKEND_CORS_ORIGINS: "https://yourdomain.com"
      MODEL_DIR: "./data/models"
    ports:
      - "8000:8000"

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    container_name: foodwaste_frontend
    restart: always
    depends_on:
      - backend
    ports:
      - "80:80"

volumes:
  pgdata:
```

---

## 4. Bare-Metal / Linux VM Deployment (Systemd + Nginx)

For standard Ubuntu/Debian Linux virtual machines (e.g., AWS EC2, GCP Compute Engine, Azure VM):

### 4.1 Systemd Service Unit (`/etc/systemd/system/foodwaste.service`)
```ini
[Unit]
Description=AI-Powered Food Waste Management Platform Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/foodwaste
EnvironmentFile=/var/www/foodwaste/.env
ExecStart=/var/www/foodwaste/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable foodwaste
sudo systemctl start foodwaste
```

### 4.2 Nginx Site Configuration (`/etc/nginx/sites-available/foodwaste`)
```nginx
server {
    listen 80;
    server_name foodwaste.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name foodwaste.example.com;

    ssl_certificate /etc/letsencrypt/live/foodwaste.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/foodwaste.example.com/privkey.pem;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Frontend Single Page App
    root /var/www/foodwaste/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # API Proxy to FastAPI Backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health Checks
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

---

## 5. Health Probes & Monitoring

Configure your load balancer or container orchestrator with these health probes:

| Probe Type | URL Path | Method | Expected HTTP Code | Notes |
| :--- | :--- | :---: | :---: | :--- |
| **Liveness Probe** | `/health` | `GET` | `200` | Checks whether the Uvicorn/FastAPI process is accepting HTTP traffic. |
| **Readiness Probe** | `/health/ready` | `GET` | `200` | Performs a live database query (`SELECT 1`). Returns `503 Service Unavailable` if database is down. |
| **ML Inference Probe** | `/api/v1/forecasts/health` | `GET` | `200` | Verifies that champion Scikit-Learn models are loaded in memory. |

---

## 6. Zero-Downtime Release Procedure

When applying updates to production:

1. **Pull Code**: Checkout verified release tag or commit.
2. **Install Dependencies**: `pip install -r backend/requirements.txt` and `npm --prefix frontend ci`.
3. **Compile Frontend**: `npm --prefix frontend run build`.
4. **Apply Migrations**: `cd backend && alembic upgrade head && cd ..`.
5. **Reload Backend Workers**: Gracefully reload Uvicorn workers (`systemctl reload foodwaste` or rolling container update).
6. **Verify Probes**: Validate `/health/ready` and test end-to-end user login before redirecting client traffic.
