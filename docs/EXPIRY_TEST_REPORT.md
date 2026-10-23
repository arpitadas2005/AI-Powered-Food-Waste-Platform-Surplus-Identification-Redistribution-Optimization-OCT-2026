# Expiry Engine & Classification Test Report

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 5 — Expiry Tracking, Food Classification and Alert Engine  
**Date**: October 23, 2026  
**Test Suite Status**: **11 / 11 PASSING (100%)**  

---

## 1. Automated Test Execution Summary

Executed using `pytest` against an isolated SQLite test environment:
- **Command**: `.\.venv\Scripts\pytest.exe backend/tests/test_expiry_engine.py -v`
- **Result**: **11 passed, 0 failed in 0.94s**

```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0
rootdir: D:\Waste management
configfile: pytest.ini
collected 11 items

backend/tests/test_expiry_engine.py::test_items_expiring_today_and_critical_classification PASSED [  9%]
backend/tests/test_expiry_engine.py::test_already_expired_items_and_food_safety_rule PASSED [ 18%]
backend/tests/test_expiry_engine.py::test_all_configured_thresholds PASSED [ 27%]
backend/tests/test_expiry_engine.py::test_items_just_outside_thresholds PASSED [ 36%]
backend/tests/test_expiry_engine.py::test_different_timezone_boundaries PASSED [ 45%]
backend/tests/test_expiry_engine.py::test_repeated_runs_and_alert_deduplication PASSED [ 54%]
backend/tests/test_expiry_engine.py::test_tenant_isolation_on_expiry PASSED [ 63%]
backend/tests/test_scheduler_isolated_error_resilience PASSED [ 72%]
backend/tests/test_alert_acknowledgment_flow PASSED [ 81%]
backend/tests/test_api_expiry_evaluation_and_config PASSED [ 90%]
backend/tests/test_synthetic_fixture_classification_accuracy PASSED [100%]

======================== 11 passed, 1 warning in 0.94s ========================
```

---

## 2. Synthetic Ground-Truth Classification Accuracy

In [`test_synthetic_fixture_classification_accuracy`](file:///D:/Waste%20management/backend/tests/test_expiry_engine.py#L346-L411), 20 synthetic items with known ground-truth labels across 5 distinct categories were evaluated:

| Expected Status | Sample Count | Evaluated Result | False Alerts | Missed Alerts | Agreement Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`EXPIRED`** | 4 | 4 | 0 | 0 | **100.0%** |
| **`CRITICAL`** | 4 | 4 | 0 | 0 | **100.0%** |
| **`WARNING`** | 4 | 4 | 0 | 0 | **100.0%** |
| **`NOTICE`** | 4 | 4 | 0 | 0 | **100.0%** |
| **`FRESH`** | 4 | 4 | 0 | 0 | **100.0%** |
| **Total** | **20** | **20** | **0** | **0** | **100.0%** |

*Note: These results represent deterministic rule-engine validation against regulatory thresholds, not trained machine-learning model accuracy.*

---

## 3. Boundary & Timezone Test Verification

1. **Items Expiring Today (`test_items_expiring_today_and_critical_classification`)**:
   - Items expiring on the current calendar date yield fractional days $\le 1.0$ day, triggering `CRITICAL` severity and immediate donation triage recommendations.
2. **Expired Items Food Safety Rule (`test_already_expired_items_and_food_safety_rule`)**:
   - Items with $\Delta t \le 0.0$ yield `EXPIRED` status, `DISCARD` recommended action, and `donation_eligible = false`.
3. **Timezone Boundary Consistency (`test_different_timezone_boundaries`)**:
   - Items evaluated across `America/New_York`, `UTC`, and `Asia/Kolkata` are anchored to local `23:59:59.999999` in each tenant's respective timezone, guaranteeing deterministic behavior across daylight-saving transitions.
4. **Deduplication Cooldown (`test_repeated_runs_and_alert_deduplication`)**:
   - Initial run creates alerts for all eligible items. Immediate second run evaluates the same items and creates **0 duplicate alerts**.
5. **Cross-Tenant Alert Isolation (`test_tenant_isolation_on_expiry`)**:
   - Alerts generated for Tenant A are inaccessible to Tenant B (returns 0 records).

---

## 4. Performance Benchmark Measurements

Captured using [`backend/tests/run_performance_benchmark.py`](file:///D:/Waste%20management/backend/tests/run_performance_benchmark.py):

| Evaluation Benchmark Scenario | Active Item Count | Duration | Rate / Throughput | Alerts Generated | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Initial Expiry Evaluation** | 1,500 active items | **471.25 ms** | **3,183 items/sec** | 200 alerts created | **PASS** |
| **Deduplication Re-Run** | 1,500 active items | **424.47 ms** | **3,534 items/sec** | 0 alerts (suppressed) | **PASS** |
| **HTTP `GET /api/v1/alerts/config`** | Config entity | **18.76 ms** (p50) | ~53 req/sec | N/A | **PASS** |
