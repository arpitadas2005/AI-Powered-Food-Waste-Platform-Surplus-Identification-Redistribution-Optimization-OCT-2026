# Feature Engineering & Leakage Prevention Report

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 2 — Machine Learning Demand Forecasting & Food Waste Prediction  
**Phase**: Phase 2 — Data Cleaning, Preprocessing, Feature Engineering & ML-Ready Dataset Generation  
**Date**: October 24, 2026  
**Auditor**: Senior Machine Learning Engineer, Data Engineer, QA Engineer  

---

## 1. Feature Architecture Overview

Forecasting perishable food demand and shelf-life expiration risk requires features that capture:
1. Short-term autoregressive momentum.
2. Weekly and monthly seasonal rhythms.
3. Operational stock availability constraints (preventing stockout-induced demand distortion).
4. Economic prioritization (protecting high-margin and highly perishable goods).

To guarantee that the models generalize without data leakage, all feature transformations strictly adhere to the **Zero-Leakage Invariant**:
$$\mathbf{x}_{i, t} = \mathcal{F}\left(\{y_{i, \tau}, w_{i, \tau}, I_{i, \tau}\}_{\tau \le t-1}, \mathbf{c}_t, \mathbf{m}_i\right)$$
where $y$ is sales, $w$ is waste, $I$ is closing inventory balance, $\mathbf{c}_t$ is calendar context on day $t$, and $\mathbf{m}_i$ is static item metadata.

---

## 2. Complete Feature Dictionary (27 Engineered Features)

The feature engine ([`backend/app/ml/feature_engine.py`](file:///D:/Waste%20management/backend/app/ml/feature_engine.py)) generates 27 predictive features across 4 families:

### Family A: Autoregressive Lag Features (5 Features)
| Feature Name | Formulation | Lookback Horizon | Business / Predictive Justification |
| :--- | :--- | :---: | :--- |
| `lag_1` | $y_{t-1}$ | 1 Day | Immediate prior-day sales momentum. |
| `lag_2` | $y_{t-2}$ | 2 Days | Two-day demand persistence. |
| `lag_7` | $y_{t-7}$ | 7 Days | Same-day-of-week demand from previous week (primary weekly seasonal anchor). |
| `lag_14` | $y_{t-14}$ | 14 Days | Same-day demand from two weeks prior (fortnightly shopping cadence). |
| `lag_28` | $y_{t-28}$ | 28 Days | Same-day demand from four weeks prior (monthly payday cadence). |

### Family B: Rolling Window Statistics (7 Features)
All rolling windows apply `shift(1)` **prior** to aggregation, preventing the current day's sales from entering the window:
| Feature Name | Formulation | Window Size | Business / Predictive Justification |
| :--- | :--- | :---: | :--- |
| `rolling_mean_7` | $\frac{1}{7}\sum_{i=1}^7 y_{t-i}$ | 7 Days | Smooth 1-week baseline demand velocity. |
| `rolling_std_7` | $\sqrt{\frac{1}{6}\sum_{i=1}^7 (y_{t-i} - \bar{y})^2}$ | 7 Days | Short-term demand volatility and uncertainty. |
| `rolling_mean_14`| $\frac{1}{14}\sum_{i=1}^{14} y_{t-i}$ | 14 Days | Fortnightly baseline demand trend. |
| `rolling_mean_28`| $\frac{1}{28}\sum_{i=1}^{28} y_{t-i}$ | 28 Days | Long-term monthly baseline consumption. |
| `rolling_max_7` | $\max(y_{t-1}, \dots, y_{t-7})$ | 7 Days | Peak single-day recent customer demand. |
| `rolling_min_7` | $\min(y_{t-1}, \dots, y_{t-7})$ | 7 Days | Minimum single-day recent consumption floor. |
| `rolling_waste_7`| $\frac{1}{7}\sum_{i=1}^7 w_{t-i}$ | 7 Days | Recent historical shelf spoilage rate for expiration risk modeling. |

### Family C: Inventory & Financial Context (7 Features)
| Feature Name | Formulation | Lookback Horizon | Business / Predictive Justification |
| :--- | :--- | :---: | :--- |
| `prior_day_stock` | $I_{t-1}$ | 1 Day | Physical stock available entering the forecast date. |
| `prior_day_stockout` | $\mathbb{I}(I_{t-1} \le 0)$ | 1 Day | Flags whether prior sales were artificially suppressed by an out-of-stock event. |
| `shelf_life_days` | Static parameter | Static | Biological lifespan before expiration (e.g. 5 days for fish vs 14 days for apples). |
| `unit_cost` | Wholesale cost | Static/Time-varying | Procurement expenditure per unit. |
| `selling_price` | Retail shelf price | Static/Time-varying | Customer shelf price per unit. |
| `gross_margin` | $\max(0, P - C)$ | Financial | Unit profit contribution. |
| `gross_margin_ratio` | $(P - C) / P$ | Financial | Relative profit margin percentage. |

### Family D: Calendar & Seasonality Indicators (8 Features)
| Feature Name | Formulation | Domain | Business / Predictive Justification |
| :--- | :--- | :---: | :--- |
| `day_of_week` | $\text{date.day\_of\_week}$ | $[0, 6]$ | Day of week (0 = Monday, 6 = Sunday). |
| `is_weekend` | $\mathbb{I}(\text{day\_of\_week} \in [5, 6])$ | $\{0, 1\}$ | Supermarket foot-traffic surges on Saturday/Sunday. |
| `day_of_month` | $\text{date.day}$ | $[1, 31]$ | Payday cycles (beginning and end of calendar month). |
| `month` | $\text{date.month}$ | $[1, 12]$ | Annual seasonality (holidays, harvest cycles). |
| `is_month_start` | $\mathbb{I}(\text{day} = 1)$ | $\{0, 1\}$ | Month-start restocking and consumer budget resets. |
| `is_month_end` | $\mathbb{I}(\text{day} = \text{last\_day})$ | $\{0, 1\}$ | End-of-month clearance patterns. |
| `sin_dow` | $\sin(2\pi \cdot \text{dow} / 7)$ | $[-1.0, 1.0]$ | Continuous circular encoding of day-of-week seasonality. |
| `cos_dow` | $\cos(2\pi \cdot \text{dow} / 7)$ | $[-1.0, 1.0]$ | Continuous circular encoding of day-of-week seasonality. |

---

## 3. Warm-up Period Handling

Because the maximum autoregressive lookback is 28 days (`lag_28`, `rolling_mean_28`), the first 28 calendar days for each SKU cannot compute complete 28-day lags.

To prevent missing data corruption:
- Each row is tagged with `is_warmup = (day_index < 28)`.
- The dataset splitter automatically excludes `is_warmup` rows from the training split (`data/processed/train_features.csv`).
- The training split retains **4,313 clean, non-warmup observation rows** (from day 29 to day 255).
- Validation and Test splits contain zero warm-up rows (as they occur well after day 255).

---

## 4. Multi-Horizon Forecasting Targets

The target builder ([`backend/app/ml/target_builder.py`](file:///D:/Waste%20management/backend/app/ml/target_builder.py)) constructs 4 distinct future targets:

| Target Column | Mathematical Definition | Forecast Horizon | Production Application |
| :--- | :--- | :---: | :--- |
| `target_sales_1d` | $y_{t+1}$ | 1 Day Ahead | Next-day automated shelf restocking and rapid reordering. |
| `target_sales_7d` | $y_{t+7}$ | 7 Days Ahead | Same-day weekly supplier purchasing order placement. |
| `target_demand_7d_sum` | $\sum_{k=1}^7 y_{t+k}$ | 7-Day Cumulative | Weekly batch inventory replenishment planning. |
| `target_waste_7d_sum` | $\sum_{k=1}^7 w_{t+k}$ | 7-Day Cumulative | Expiration risk scoring and dynamic price markdown triggering. |

---

## 5. Automated Verification of Zero Leakage

In [`backend/tests/test_ml_preprocessing_pipeline.py`](file:///D:/Waste%20management/backend/tests/test_ml_preprocessing_pipeline.py), `test_feature_engine_strict_zero_lookahead_leakage` programmatically validates zero lookahead leakage:

1. A copy of the benchmark dataset is generated.
2. An extreme sales spike (`recorded_sales = 99,999.0`) is injected at day index 30.
3. Feature engineering is executed across the perturbed timeline.
4. The feature vectors at day index 25 (prior to perturbation) are compared against the unperturbed feature vectors.
5. **Result**: 100% bit-for-bit identical across all 27 features (`PASS`). Zero future information is accessible to past features.
