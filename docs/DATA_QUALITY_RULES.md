# Data Quality Rules & Error Code Catalog

**Project**: AI-Powered Food Waste Management Platform for Surplus Identification and Redistribution Optimization  
**Milestone**: 1 — Inventory Management & Expiry Tracking System  
**Phase**: Phase 4 — CSV Ingestion and Data Quality  
**Status**: APPROVED SPECIFICATION  

---

## 1. Overview

This document specifies the validation criteria, data cleaning algorithms, normalization rules, and standardized error codes enforced by the CSV data quality engine.

---

## 2. Normalization & Sanitization Algorithms

### 2.1 String & Text Cleaning
- **Whitespace Normalization**: Leading and trailing whitespace is stripped from all headers and cells. Empty strings are converted to `None` for optional fields.
- **CSV Formula Injection Sanitization (CWE-1236)**:
  ```python
  CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
  def sanitize_csv_cell(value: Any) -> Any:
      if isinstance(value, str) and value:
          stripped = value.strip()
          if stripped.startswith(CSV_DANGEROUS_PREFIXES):
              return f"'{stripped}"
          return stripped
      return value
  ```

### 2.2 Category Resolution
- Category lookup matches input against:
  1. Canonical Category Slug (e.g. `dairy-and-eggs`)
  2. Category Display Name (e.g. `Dairy & Eggs`)
  3. Category UUID (e.g. `cat_dairy_eggs`)
- Matches are case-insensitive and whitespace-insensitive.
- Unmatched categories trigger `UNKNOWN_CATEGORY`.

### 2.3 Unit Standardization
- Units are converted to lowercase.
- Allowed values: `kg`, `g`, `liters`, `ml`, `units`, `boxes`, `packs`.
- Any non-standard unit triggers `INVALID_UNIT`.

### 2.4 Date Parsing & Chronological Validation
- Format strictly required: `YYYY-MM-DD` (ISO-8601).
- Non-existent dates (e.g. `2026-02-31`, `2027-02-29`) trigger `INVALID_DATE_FORMAT`.
- Future purchase dates (`purchase_date > today`) trigger `FUTURE_PURCHASE_DATE`.
- Chronological ordering requirement: `expiry_date >= purchase_date`. Expiry dates preceding purchase dates trigger `EXPIRY_BEFORE_PURCHASE`.

---

## 3. Standardized Error Code Catalog

| Error Code | Field Name | Description & Trigger Criteria | Example Invalid Value |
| :--- | :--- | :--- | :--- |
| `INVALID_NAME` | `name` | Name is empty, whitespace, or shorter than 2 characters. | `""` or `" "` |
| `MISSING_CATEGORY` | `category` | Category column is blank or missing. | `""` |
| `UNKNOWN_CATEGORY` | `category` | Category value does not match any active standard or tenant category. | `space-food` |
| `MISSING_QUANTITY` | `current_quantity` | Quantity field is empty. | `""` |
| `INVALID_QUANTITY` | `current_quantity` | Quantity is non-numeric or negative. | `-10.5` or `ten` |
| `MISSING_UNIT` | `unit` | Unit field is empty. | `""` |
| `INVALID_UNIT` | `unit` | Unit does not belong to accepted set (`kg`, `g`, `liters`, etc.). | `gallons` |
| `MISSING_PURCHASE_DATE` | `purchase_date` | Purchase date field is empty. | `""` |
| `INVALID_PURCHASE_DATE` | `purchase_date` | Purchase date does not conform to `YYYY-MM-DD`. | `10/22/2026` |
| `FUTURE_PURCHASE_DATE` | `purchase_date` | Purchase date is in the future. | `2099-01-01` |
| `MISSING_EXPIRY_DATE` | `expiry_date` | Expiry date field is empty. | `""` |
| `INVALID_EXPIRY_DATE` | `expiry_date` | Expiry date does not conform to `YYYY-MM-DD`. | `tomorrow` |
| `EXPIRY_BEFORE_PURCHASE`| `expiry_date` | Expiry date occurs before purchase date. | `purchase: 2026-10-22`, `expiry: 2026-10-20` |
| `DUPLICATE_SKU_IN_FILE`| `sku` | SKU appears more than once within the same uploaded CSV file. | Duplicate `SKU-001` on row 4 and row 12 |
| `EXISTING_SKU_CONFLICT`| `sku` | SKU conflicts with an existing active inventory item for the tenant. | `DAI-MILK-001` (already in DB) |
| `INVALID_COST` | `cost_per_unit` | Cost per unit is negative or non-numeric. | `-1.25` |
| `INVALID_PRICE` | `selling_price` | Selling price is negative or non-numeric. | `-2.50` |
| `INVALID_STORAGE` | `storage_requirement` | Storage does not match `AMBIENT`, `REFRIGERATED`, `FROZEN`, `DRY_PANTRY`. | `underwater` |
| `ROW_LIMIT_EXCEEDED` | File Level | CSV contains more than 10,000 data rows. | 10,001 rows |
| `FILE_SIZE_EXCEEDED` | File Level | File size exceeds 10 MB limit. | 11.2 MB file |
| `MISSING_HEADERS` | File Level | Required headers (`name`, `category`, `current_quantity`, `unit`, `purchase_date`, `expiry_date`) missing. | Missing `unit` column |
| `MALFORMED_ENCODING` | File Level | File bytes cannot be decoded as UTF-8 or Latin-1. | Corrupted binary |
