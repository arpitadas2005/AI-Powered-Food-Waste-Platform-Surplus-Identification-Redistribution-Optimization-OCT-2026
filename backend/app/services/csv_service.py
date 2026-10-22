"""Robust CSV Inventory Ingestion Pipeline and Data Quality Service."""

import csv
from datetime import datetime, timezone
import io
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.category import Category, StorageRequirement
from backend.app.models.csv_import import (
    CsvImportJob,
    CsvImportRowError,
    CsvImportStatus,
)
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.transaction import (
    ReferenceType,
    StockTransaction,
    TransactionType,
)
from backend.app.schemas.csv_import import (
    CsvImportResponse,
    CsvImportRowErrorSchema,
    CsvImportSummary,
)
from backend.app.services.inventory_service import derive_status

# Constants & Ingestion Constraints
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROW_COUNT = 10_000
CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

REQUIRED_HEADERS = {
    "name",
    "category",
    "current_quantity",
    "unit",
    "purchase_date",
    "expiry_date",
}

OPTIONAL_HEADERS = {
    "sku",
    "barcode",
    "cost_per_unit",
    "selling_price",
    "batch_number",
    "storage_requirement",
    "storage_location",
}

VALID_UNITS = {u.value for u in ItemUnit}
VALID_STORAGES = {s.value for s in StorageRequirement}


class CsvIngestionError(Exception):
    """Base exception for CSV file ingestion."""
    pass


class FileSizeLimitExceededError(CsvIngestionError):
    """Raised when file exceeds size limit."""
    pass


class RowLimitExceededError(CsvIngestionError):
    """Raised when CSV contains more than MAX_ROW_COUNT rows."""
    pass


class MalformedEncodingError(CsvIngestionError):
    """Raised when file encoding cannot be decoded."""
    pass


class MissingHeadersError(CsvIngestionError):
    """Raised when required headers are missing."""
    pass


def sanitize_csv_cell(value: Any) -> Any:
    """
    Sanitize text input to prevent CSV Formula Injection (CWE-1236).
    Prepends a single quote if string begins with dangerous spreadsheet execution prefixes.
    """
    if isinstance(value, str) and value:
        stripped = value.strip()
        if stripped.startswith(CSV_DANGEROUS_PREFIXES):
            return f"'{stripped}"
        return stripped
    return value


def generate_template_csv() -> str:
    """Generates standard CSV import template with headers and realistic sample rows."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    headers = [
        "name",
        "category",
        "sku",
        "barcode",
        "current_quantity",
        "unit",
        "cost_per_unit",
        "selling_price",
        "purchase_date",
        "expiry_date",
        "batch_number",
        "storage_requirement",
        "storage_location",
    ]
    writer.writerow(headers)
    sample_rows = [
        [
            "Organic Whole Milk 1L",
            "dairy-and-eggs",
            "DAI-MILK-001",
            "012345678905",
            "50.0",
            "liters",
            "1.20",
            "2.49",
            "2026-10-22",
            "2026-10-28",
            "LOT-2026-A",
            "REFRIGERATED",
            "Walk-in Chiller 1",
        ],
        [
            "Fresh Atlantic Salmon Fillet",
            "seafood-and-fish",
            "SEA-SALM-002",
            "012345678912",
            "20.0",
            "kg",
            "14.50",
            "22.00",
            "2026-10-22",
            "2026-10-24",
            "BATCH-SEA-44",
            "REFRIGERATED",
            "Seafood Display",
        ],
        [
            "Artisan Sourdough Bread",
            "fresh-bakery-and-pastries",
            "BAK-SOUR-003",
            "012345678929",
            "30.0",
            "units",
            "1.50",
            "3.99",
            "2026-10-22",
            "2026-10-25",
            "BAK-DAY-22",
            "AMBIENT",
            "Bakery Counter",
        ],
    ]
    for row in sample_rows:
        writer.writerow(row)
    return output.getvalue()


def decode_csv_content(file_bytes: bytes) -> str:
    """
    Safely decodes raw file bytes into string.
    Checks encodings: utf-8-sig (with BOM), utf-8, ascii, and iso-8859-1.
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileSizeLimitExceededError(
            f"File size ({len(file_bytes)} bytes) exceeds maximum allowed size ({MAX_FILE_SIZE_BYTES} bytes)"
        )

    for encoding in ("utf-8-sig", "utf-8", "ascii"):
        try:
            return file_bytes.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise MalformedEncodingError(
        "File is not valid UTF-8 or ASCII encoded text. Please save your file as UTF-8 CSV."
    )


def load_category_lookup(db: Session, tenant_id: str) -> Dict[str, Category]:
    """
    Builds a case-insensitive lookup table matching category slug and name to Category objects.
    """
    categories = db.execute(
        select(Category).where(
            or_(Category.tenant_id == tenant_id, Category.tenant_id == None)
        )
    ).scalars().all()

    lookup: Dict[str, Category] = {}
    for cat in categories:
        lookup[cat.slug.lower().strip()] = cat
        lookup[cat.name.lower().strip()] = cat
        lookup[cat.id.lower().strip()] = cat
    return lookup


def load_existing_skus(db: Session, tenant_id: str) -> Set[str]:
    """Returns set of existing active SKUs in the tenant's inventory."""
    rows = db.execute(
        select(InventoryItem.sku).where(
            InventoryItem.tenant_id == tenant_id,
            InventoryItem.sku != None,
            InventoryItem.is_active == True,
        )
    ).scalars().all()
    return {r.strip().lower() for r in rows if r}


def process_csv_import(
    db: Session,
    tenant_id: str,
    user_id: str,
    filename: str,
    file_bytes: bytes,
    dry_run: bool = True,
    allow_partial: bool = False,
) -> CsvImportResponse:
    """
    Executes the multi-stage ingestion pipeline:
    1. Validation of size and encoding.
    2. Header parsing and mapping.
    3. Row-level validation and normalization.
    4. Duplicate and conflict detection.
    5. Dry-run simulation or transactional persistence.
    6. Structured diagnostic report generation.
    """
    file_size = len(file_bytes)
    content = decode_csv_content(file_bytes)

    # Check for empty file
    if not content.strip():
        raise CsvIngestionError("The uploaded CSV file is empty")

    reader = csv.reader(io.StringIO(content))
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise CsvIngestionError("CSV file has no content or headers")

    # Normalize headers
    normalized_headers = [h.strip().lower() for h in raw_headers if h]
    header_set = set(normalized_headers)

    missing_required = REQUIRED_HEADERS - header_set
    if missing_required:
        raise MissingHeadersError(
            f"Missing required columns: {', '.join(sorted(missing_required))}. "
            f"Provided headers: {', '.join(normalized_headers)}"
        )

    # Pre-load category mappings and existing SKUs for fast in-memory validation
    category_lookup = load_category_lookup(db, tenant_id)
    existing_tenant_skus = load_existing_skus(db, tenant_id)

    # Ingestion State
    dict_reader = csv.DictReader(io.StringIO(content))
    row_errors: List[CsvImportRowErrorSchema] = []
    valid_items: List[Dict[str, Any]] = []
    file_seen_skus: Set[str] = set()

    total_rows = 0
    duplicate_count = 0

    for idx, raw_row in enumerate(dict_reader, start=2):  # Row 1 is header
        total_rows += 1
        if total_rows > MAX_ROW_COUNT:
            raise RowLimitExceededError(
                f"CSV row count exceeds maximum limit of {MAX_ROW_COUNT} rows"
            )

        row_has_error = False

        # Clean row dictionary keys and values
        row: Dict[str, str] = {
            (k.strip().lower() if k else ""): (v.strip() if v else "")
            for k, v in raw_row.items()
            if k
        }

        # 1. Validate Product Name
        name = row.get("name", "")
        if not name or len(name) < 2:
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="name",
                    invalid_value=name,
                    error_code="INVALID_NAME",
                    error_message="Item name must be between 2 and 255 characters",
                )
            )
            row_has_error = True

        # 2. Validate Category
        cat_key = row.get("category", "").lower()
        matched_cat = category_lookup.get(cat_key)
        if not matched_cat:
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="category",
                    invalid_value=row.get("category", ""),
                    error_code="UNKNOWN_CATEGORY",
                    error_message=f"Category '{row.get('category', '')}' is not recognized in taxonomy",
                )
            )
            row_has_error = True

        # 3. Validate Quantity
        raw_qty = row.get("current_quantity", "")
        quantity = 0.0
        try:
            quantity = float(raw_qty)
            if quantity < 0.0:
                raise ValueError()
        except (ValueError, TypeError):
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="current_quantity",
                    invalid_value=raw_qty,
                    error_code="INVALID_QUANTITY",
                    error_message="Quantity must be a non-negative number",
                )
            )
            row_has_error = True

        # 4. Validate Unit
        unit = row.get("unit", "").lower()
        if unit not in VALID_UNITS:
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="unit",
                    invalid_value=unit,
                    error_code="INVALID_UNIT",
                    error_message=f"Unit '{unit}' is invalid. Allowed: {', '.join(sorted(VALID_UNITS))}",
                )
            )
            row_has_error = True

        # 5. Validate Dates
        raw_purchase = row.get("purchase_date", "")
        purchase_date = None
        try:
            purchase_date = datetime.strptime(raw_purchase, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="purchase_date",
                    invalid_value=raw_purchase,
                    error_code="INVALID_DATE_FORMAT",
                    error_message="purchase_date must follow YYYY-MM-DD format",
                )
            )
            row_has_error = True

        raw_expiry = row.get("expiry_date", "")
        expiry_date = None
        try:
            expiry_date = datetime.strptime(raw_expiry, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="expiry_date",
                    invalid_value=raw_expiry,
                    error_code="INVALID_DATE_FORMAT",
                    error_message="expiry_date must follow YYYY-MM-DD format",
                )
            )
            row_has_error = True

        if purchase_date and expiry_date and expiry_date < purchase_date:
            row_errors.append(
                CsvImportRowErrorSchema(
                    row_number=idx,
                    field_name="expiry_date",
                    invalid_value=raw_expiry,
                    error_code="EXPIRY_BEFORE_PURCHASE",
                    error_message=f"expiry_date ({raw_expiry}) cannot be earlier than purchase_date ({raw_purchase})",
                )
            )
            row_has_error = True

        # 6. Validate SKU & Detect Duplicates
        sku = row.get("sku", "")
        if sku:
            sku_lower = sku.lower()
            if sku_lower in file_seen_skus:
                row_errors.append(
                    CsvImportRowErrorSchema(
                        row_number=idx,
                        field_name="sku",
                        invalid_value=sku,
                        error_code="DUPLICATE_SKU_IN_FILE",
                        error_message=f"SKU '{sku}' appears multiple times within this CSV file",
                    )
                )
                duplicate_count += 1
                row_has_error = True
            elif sku_lower in existing_tenant_skus:
                row_errors.append(
                    CsvImportRowErrorSchema(
                        row_number=idx,
                        field_name="sku",
                        invalid_value=sku,
                        error_code="SKU_ALREADY_EXISTS",
                        error_message=f"SKU '{sku}' already exists in your active inventory",
                    )
                )
                duplicate_count += 1
                row_has_error = True
            else:
                file_seen_skus.add(sku_lower)

        # 7. Optional Pricing validation
        raw_cost = row.get("cost_per_unit", "")
        cost = 0.0
        if raw_cost:
            try:
                cost = float(raw_cost)
                if cost < 0.0:
                    raise ValueError()
            except ValueError:
                row_errors.append(
                    CsvImportRowErrorSchema(
                        row_number=idx,
                        field_name="cost_per_unit",
                        invalid_value=raw_cost,
                        error_code="INVALID_COST",
                        error_message="cost_per_unit must be a non-negative number",
                    )
                )
                row_has_error = True

        raw_price = row.get("selling_price", "")
        price = None
        if raw_price:
            try:
                price = float(raw_price)
                if price < 0.0:
                    raise ValueError()
            except ValueError:
                row_errors.append(
                    CsvImportRowErrorSchema(
                        row_number=idx,
                        field_name="selling_price",
                        invalid_value=raw_price,
                        error_code="INVALID_PRICE",
                        error_message="selling_price must be a non-negative number",
                    )
                )
                row_has_error = True

        # 8. Storage Requirement validation & inheritance
        storage = row.get("storage_requirement", "").upper()
        if storage:
            if storage not in VALID_STORAGES:
                row_errors.append(
                    CsvImportRowErrorSchema(
                        row_number=idx,
                        field_name="storage_requirement",
                        invalid_value=storage,
                        error_code="INVALID_STORAGE",
                        error_message=f"Storage requirement '{storage}' is invalid",
                    )
                )
                row_has_error = True
        elif matched_cat:
            storage = matched_cat.recommended_storage

        # Accumulate valid record if clean
        if not row_has_error and matched_cat and purchase_date and expiry_date:
            valid_items.append({
                "name": sanitize_csv_cell(name),
                "category_id": matched_cat.id,
                "sku": sanitize_csv_cell(sku) if sku else None,
                "barcode": sanitize_csv_cell(row.get("barcode")) if row.get("barcode") else None,
                "current_quantity": quantity,
                "unit": unit,
                "cost_per_unit": cost,
                "selling_price": price,
                "purchase_date": purchase_date,
                "expiry_date": expiry_date,
                "batch_number": sanitize_csv_cell(row.get("batch_number")) if row.get("batch_number") else None,
                "storage_requirement": storage,
                "storage_location": sanitize_csv_cell(row.get("storage_location")) if row.get("storage_location") else None,
                "status": derive_status(expiry_date, quantity),
            })

    # Summary Counts
    rejected_count = len({e.row_number for e in row_errors})
    accepted_count = len(valid_items)
    skipped_count = 0

    # Decision Logic: Commit vs Rollback vs Dry Run
    if dry_run:
        status_str = (
            CsvImportStatus.DRY_RUN_PASSED.value
            if rejected_count == 0
            else CsvImportStatus.DRY_RUN_FAILED.value
        )
        # Create Job Audit Record
        job = CsvImportJob(
            tenant_id=tenant_id,
            filename=filename,
            file_size_bytes=file_size,
            total_rows=total_rows,
            successful_rows=accepted_count,
            failed_rows=rejected_count,
            status=status_str,
            dry_run=True,
            allow_partial=allow_partial,
            created_by_user_id=user_id,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        return CsvImportResponse(
            job_id=job.id,
            filename=filename,
            file_size_bytes=file_size,
            dry_run=True,
            allow_partial=allow_partial,
            status=status_str,
            summary=CsvImportSummary(
                total_rows=total_rows,
                accepted_rows=accepted_count,
                rejected_rows=rejected_count,
                skipped_rows=0,
                duplicate_rows=duplicate_count,
            ),
            errors=row_errors,
            sample_imported_items=valid_items[:5] if valid_items else None,
        )

    # Live Commit Execution
    if rejected_count > 0 and not allow_partial:
        # Strict mode: All-or-nothing rollback
        status_str = CsvImportStatus.FAILED.value
        job = CsvImportJob(
            tenant_id=tenant_id,
            filename=filename,
            file_size_bytes=file_size,
            total_rows=total_rows,
            successful_rows=0,
            failed_rows=rejected_count,
            status=status_str,
            dry_run=False,
            allow_partial=False,
            created_by_user_id=user_id,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()

        for err in row_errors:
            db_err = CsvImportRowError(
                job_id=job.id,
                tenant_id=tenant_id,
                row_number=err.row_number,
                field_name=err.field_name,
                invalid_value=err.invalid_value,
                error_code=err.error_code,
                error_message=err.error_message,
            )
            db.add(db_err)

        db.commit()

        return CsvImportResponse(
            job_id=job.id,
            filename=filename,
            file_size_bytes=file_size,
            dry_run=False,
            allow_partial=False,
            status=status_str,
            summary=CsvImportSummary(
                total_rows=total_rows,
                accepted_rows=0,
                rejected_rows=rejected_count,
                skipped_rows=accepted_count,
                duplicate_rows=duplicate_count,
            ),
            errors=row_errors,
        )

    # Permissive or Clean Commit Mode: Save Valid Rows
    job = CsvImportJob(
        tenant_id=tenant_id,
        filename=filename,
        file_size_bytes=file_size,
        total_rows=total_rows,
        successful_rows=accepted_count,
        failed_rows=rejected_count,
        status=(
            CsvImportStatus.COMPLETED.value
            if accepted_count > 0
            else CsvImportStatus.FAILED.value
        ),
        dry_run=False,
        allow_partial=allow_partial,
        created_by_user_id=user_id,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()

    for item_dict in valid_items:
        new_item = InventoryItem(
            tenant_id=tenant_id,
            category_id=item_dict["category_id"],
            name=item_dict["name"],
            sku=item_dict["sku"],
            barcode=item_dict["barcode"],
            current_quantity=item_dict["current_quantity"],
            unit=item_dict["unit"],
            cost_per_unit=item_dict["cost_per_unit"],
            selling_price=item_dict["selling_price"],
            purchase_date=item_dict["purchase_date"],
            expiry_date=item_dict["expiry_date"],
            batch_number=item_dict["batch_number"],
            storage_requirement=item_dict["storage_requirement"],
            storage_location=item_dict["storage_location"],
            status=item_dict["status"],
            is_active=True,
        )
        db.add(new_item)
        db.flush()

        # Log initial stock transaction for imported item
        tx = StockTransaction(
            tenant_id=tenant_id,
            item_id=new_item.id,
            transaction_type=TransactionType.INITIAL_COUNT.value,
            quantity_change=item_dict["current_quantity"],
            quantity_before=0.0,
            quantity_after=item_dict["current_quantity"],
            reason="CSV Bulk Import",
            reference_type=ReferenceType.CSV_IMPORT_JOB.value,
            reference_id=job.id,
            created_by_user_id=user_id,
        )
        db.add(tx)

    # Log errors if any occurred in partial mode
    for err in row_errors:
        db_err = CsvImportRowError(
            job_id=job.id,
            tenant_id=tenant_id,
            row_number=err.row_number,
            field_name=err.field_name,
            invalid_value=err.invalid_value,
            error_code=err.error_code,
            error_message=err.error_message,
        )
        db.add(db_err)

    db.commit()

    return CsvImportResponse(
        job_id=job.id,
        filename=filename,
        file_size_bytes=file_size,
        dry_run=False,
        allow_partial=allow_partial,
        status=job.status,
        summary=CsvImportSummary(
            total_rows=total_rows,
            accepted_rows=accepted_count,
            rejected_rows=rejected_count,
            skipped_rows=0,
            duplicate_rows=duplicate_count,
        ),
        errors=row_errors,
    )
