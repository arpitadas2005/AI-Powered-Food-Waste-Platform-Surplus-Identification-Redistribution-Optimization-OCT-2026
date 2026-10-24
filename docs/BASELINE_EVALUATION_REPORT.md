# Milestone 2 — Phase 3: Baseline Forecast Evaluation Report

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 2 — Machine Learning Demand Forecasting & Food Waste Prediction  
**Phase**: Phase 3 — Forecasting Model Development, Training & Evaluation  
**Date**: October 24, 2026  
**Auditor**: Senior Machine Learning Engineer, Statistical Evaluator  

---

## 1. Executive Summary

In adherence to the project's statistical evaluation plan ([`docs/ML_EVALUATION_PLAN.md`](file:///D:/Waste%20management/docs/ML_EVALUATION_PLAN.md)), simple, transparent statistical baselines were implemented and evaluated across all 19 SKU time series before training complex machine learning models.

The baselines establish the empirical minimum performance floor for all downstream predictive models.

### Key Baseline Findings
- The **Seasonal Naive ($y_{t-7}$)** baseline outperforms the **Naive ($y_{t-1}$)** baseline by **25.3% relative WAPE reduction** on 1-day ahead forecasting (Validation WAPE of 23.27% vs 31.15%), proving strong day-of-week demand cyclicity (weekend rushes vs weekday baselines).
- The **7-Day Rolling Moving Average** achieves 21.25% Validation WAPE, demonstrating that smoothing short-term daily volatility improves on simple single-day persistence.
- The **Historical SKU Mean** achieves 20.67% Validation WAPE on 1-day ahead demand and 5.63% Validation WAPE on 7-day cumulative demand.

---

## 2. Statistical Baseline Formulations & Configurations

All baselines are implemented in [`backend/app/ml/candidate_models.py`](file:///D:/Waste%20management/backend/app/ml/candidate_models.py) and [`backend/app/ml/baselines.py`](file:///D:/Waste%20management/backend/app/ml/baselines.py):

| Baseline Name | Mathematical Formulation | Lookback Context | Business / Operational Interpretation |
| :--- | :--- | :---: | :--- |
| **Naive (Persistence)** | $\hat{y}_{t+h} = y_t$ | $t-1$ | Assumes tomorrow's customer demand exactly mirrors yesterday's sales volume. |
| **Seasonal Naive** | $\hat{y}_{t+h} = y_{t+h-7}$ | $t-7$ | Assumes customer demand follows a strict 7-day weekly cycle (e.g. Saturday sales predict next Saturday). |
| **7-Day Moving Average** | $\hat{y}_{t+h} = \frac{1}{7}\sum_{i=1}^7 y_{t-i}$ | 7 Days | Dampens idiosyncratic daily noise by forecasting the recent 1-week moving average. |
| **Historical Mean** | $\hat{y}_{t+h} = \bar{y}_{\text{train}, \text{sku}}$ | In-sample Train | Uses the historical mean sales volume for that product across the entire 227-day training timeline. |

---

## 3. Empirical Baseline Evaluation Results

All baselines were evaluated on the **Validation Partition** (1,045 observations across 19 SKUs, spanning 2026-07-06 to 2026-08-29) and the held-out **Test Partition** (1,026 observations, spanning 2026-08-30 to 2026-10-23):

### 3.1 1-Day Ahead Forecast Horizon (`target_sales_1d`)

| Baseline Model | Validation WAPE (%) | Validation MASE | Validation MAE (units) | Validation RMSE (units) | Validation MBE (bias) | Test WAPE (%) | Test MASE | Test MAE (units) | Test RMSE (units) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Naive ($y_{t-1}$)** | 31.15% | 1.674 | 5.858 | 7.811 | -0.158 | 33.41% | 1.549 | 5.420 | 7.342 |
| **Seasonal Naive ($y_{t-7}$)** | **23.27%** | **1.251** | **4.376** | **6.061** | **+0.088** | **25.09%** | **1.163** | **4.070** | **5.675** |
| **Moving Average (7d)** | 21.25% | 1.142 | 3.996 | 5.303 | +0.059 | — | — | — | — |
| **Historical Mean** | 20.67% | 1.111 | 3.887 | 5.256 | -0.922 | — | — | — | — |

*Note: All baseline MASE values exceed 1.0, indicating that while seasonal naive captures day-of-week rhythm, simple persistence does not outperform the in-sample benchmark.*

### 3.2 7-Day Cumulative Demand Horizon (`target_demand_7d_sum`)

For weekly cumulative replenishment and expiry risk, predicting weekly volume ($\approx 130$ units) using single-day persistence creates extreme bias:

| Baseline Model | Validation WAPE (%) | Validation MASE | Validation MAE (units) | Validation RMSE (units) | Validation MBE (bias) | Test WAPE (%) | Test MASE |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Naive ($y_{t-1}$)** | 85.71% | 11.039 | 111.797 | 124.671 | -111.788 | 85.57% | 9.654 |
| **Seasonal Naive ($y_{t-7}$)** | 85.53% | 11.015 | 111.555 | 124.424 | -111.542 | 85.36% | 9.631 |
| **Historical Mean** | **5.63%** | **0.726** | **7.349** | **9.948** | **-4.958** | — | — |

---

## 4. Performance Breakdown by Demand Pattern

### 4.1 Smooth Demand Series (17 SKUs — Fast-Moving Staples)
- High-velocity staples (Fresh Milk, Organic Apples, Bread, Ground Beef, Chicken Breast) exhibit strong 7-day cyclicality.
- Seasonal Naive achieved **23.1% WAPE** on Smooth series.
- Naive ($y_{t-1}$) suffered from lag phase lag on weekends, achieving **30.8% WAPE**.

### 4.2 Intermittent Demand Series (2 SKUs — Gourmet & Specialty Items)
- For sparse products (`PAN-TRUF-01`, `SEA-CAVI-01`), sales occur only every 2–4 days.
- Simple daily persistence frequently predicts demand on zero days, or zero on purchase days, causing **WAPE > 45%**.
- Moving Average and Historical Mean dampens the zero-burst pattern, reducing Intermittent WAPE to **28.4%**.

---

## 5. Limitations of Statistical Baselines

1. **Inability to Learn Cross-Feature Interactions**: Baselines cannot adjust predictions based on product shelf life, current stock availability, or price elasticity.
2. **Stockout Blindness**: During inventory stockout days ($I_t = 0$), baselines persist zero demand into the next forecast period, permanently depressing replenishment orders.
3. **Static Seasonality**: Seasonal Naive assumes identical week-over-week demand and cannot adapt to multi-week trend deceleration or month-end paycheck cycles.

These empirical baseline metrics establish the exact targets that candidate machine learning models must beat to earn deployment approval.
