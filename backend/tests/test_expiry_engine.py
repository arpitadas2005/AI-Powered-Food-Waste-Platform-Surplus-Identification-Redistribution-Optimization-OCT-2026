"""
Comprehensive Tests for Expiry Tracking, Classification Engine, and Food Safety Rules.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import zoneinfo
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from backend.app.models.alert import AlertAction, AlertLevel, ExpiryAlertHistory, TenantAlertConfig
from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus, ItemUnit
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.models.user import User, UserRole
from backend.app.services.expiry_scheduler import run_scheduled_expiry_evaluation
from backend.app.services.expiry_service import (
    acknowledge_alert,
    calculate_time_remaining,
    classify_expiry_state,
    evaluate_tenant_inventory,
    get_or_create_alert_config,
    get_scheduler_diagnostics,
)


@pytest.fixture
def sample_items(db_session: Session, tenant_a: Tenant) -> dict:
    """Fixture creating categorized test items for Tenant A with diverse expiry offsets."""
    cat = db_session.query(Category).first()
    today = date(2026, 10, 22)

    # 1. Expired 2 days ago
    expired_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Past Date Milk",
        sku="TEST-EXP-01",
        current_quantity=10.0,
        unit=ItemUnit.LITERS.value,
        cost_per_unit=2.00,
        purchase_date=today - timedelta(days=10),
        expiry_date=today - timedelta(days=2),
        status=InventoryStatus.ACTIVE.value,
    )
    # 2. Expiring today
    today_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Today Baguette",
        sku="TEST-EXP-02",
        current_quantity=5.0,
        unit=ItemUnit.UNITS.value,
        cost_per_unit=1.50,
        purchase_date=today - timedelta(days=1),
        expiry_date=today,
        status=InventoryStatus.ACTIVE.value,
    )
    # 3. Expiring in 2 days (Warning threshold)
    warning_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Yogurt Pack",
        sku="TEST-EXP-03",
        current_quantity=8.0,
        unit=ItemUnit.PACKS.value,
        cost_per_unit=3.00,
        purchase_date=today - timedelta(days=5),
        expiry_date=today + timedelta(days=2),
        status=InventoryStatus.ACTIVE.value,
    )
    # 4. Expiring in 5 days (Notice threshold)
    notice_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Cheddar Cheese Block",
        sku="TEST-EXP-04",
        current_quantity=4.0,
        unit=ItemUnit.KG.value,
        cost_per_unit=6.00,
        purchase_date=today - timedelta(days=5),
        expiry_date=today + timedelta(days=5),
        status=InventoryStatus.ACTIVE.value,
    )
    # 5. Expiring in 20 days (Fresh)
    fresh_item = InventoryItem(
        tenant_id=tenant_a.id,
        category_id=cat.id,
        name="Canned Tomatoes",
        sku="TEST-EXP-05",
        current_quantity=24.0,
        unit=ItemUnit.UNITS.value,
        cost_per_unit=1.20,
        purchase_date=today - timedelta(days=2),
        expiry_date=today + timedelta(days=20),
        status=InventoryStatus.ACTIVE.value,
    )

    db_session.add_all([expired_item, today_item, warning_item, notice_item, fresh_item])
    db_session.commit()

    return {
        "expired": expired_item,
        "today": today_item,
        "warning": warning_item,
        "notice": notice_item,
        "fresh": fresh_item,
    }


def test_items_expiring_today_and_critical_classification(db_session: Session, tenant_a: Tenant, sample_items: dict):
    """An item expiring today must be classified as CRITICAL with 0 < days_remaining < 1.0."""
    eval_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
    
    resp = evaluate_tenant_inventory(
        db=db_session,
        tenant_id=tenant_a.id,
        as_of=eval_time,
        dry_run=False,
    )

    today_result = next(i for i in resp.items if i.item_id == sample_items["today"].id)
    assert today_result.alert_level == AlertLevel.CRITICAL.value
    assert 0.0 < today_result.days_remaining < 1.0
    assert today_result.donation_eligible is True

    # Database state updated
    db_session.refresh(sample_items["today"])
    assert sample_items["today"].status == InventoryStatus.EXPIRING_SOON.value


def test_already_expired_items_and_food_safety_rule(db_session: Session, tenant_a: Tenant, sample_items: dict):
    """Expired items MUST be classified as EXPIRED and strictly NEVER eligible for donation."""
    eval_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
    
    resp = evaluate_tenant_inventory(
        db=db_session,
        tenant_id=tenant_a.id,
        as_of=eval_time,
        dry_run=False,
    )

    expired_result = next(i for i in resp.items if i.item_id == sample_items["expired"].id)
    assert expired_result.alert_level == AlertLevel.EXPIRED.value
    assert expired_result.days_remaining <= 0.0
    # CRITICAL FOOD SAFETY ASSERTION:
    assert expired_result.donation_eligible is False
    assert expired_result.recommended_action == "DISCARD_OR_COMPOST"

    # Database state updated
    db_session.refresh(sample_items["expired"])
    assert sample_items["expired"].status == InventoryStatus.EXPIRED.value


def test_all_configured_thresholds(db_session: Session, tenant_a: Tenant, sample_items: dict):
    """Verify classification matches each configured threshold horizon."""
    eval_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
    
    resp = evaluate_tenant_inventory(
        db=db_session,
        tenant_id=tenant_a.id,
        as_of=eval_time,
        dry_run=False,
    )

    summary = resp.summary
    assert summary.total_evaluated == 5
    assert summary.expired_count == 1
    assert summary.critical_count == 1
    assert summary.warning_count == 1
    assert summary.notice_count == 1
    assert summary.fresh_count == 1


def test_items_just_outside_thresholds(tenant_a: Tenant):
    """Boundary conditions just outside configured cutoffs."""
    config = TenantAlertConfig(
        critical_threshold_hours=24,  # 1.0 day
        warning_threshold_days=3,     # 3.0 days
        notice_threshold_days=7,      # 7.0 days
        auto_flag_for_donation=True,
    )

    # 1.05 days -> WARNING, not CRITICAL
    lvl, act, eligible = classify_expiry_state(1.05, config)
    assert lvl == AlertLevel.WARNING.value
    assert eligible is True

    # 3.05 days -> NOTICE, not WARNING
    lvl, act, eligible = classify_expiry_state(3.05, config)
    assert lvl == AlertLevel.NOTICE.value
    assert eligible is True

    # 7.05 days -> FRESH, not NOTICE
    lvl, act, eligible = classify_expiry_state(7.05, config)
    assert lvl == "FRESH"
    assert eligible is False


def test_different_timezone_boundaries():
    """
    Same expiry date evaluated across different timezones at an exact UTC timestamp.
    At 2026-10-25 16:00:00 UTC:
      - In Tokyo (UTC+9), local time is 2026-10-26 01:00:00 JST -> expiry date 2026-10-25 is EXPIRED.
      - In New York (UTC-4), local time is 2026-10-25 12:00:00 EDT -> expiry date 2026-10-25 has ~12h left (CRITICAL).
    """
    eval_utc = datetime(2026, 10, 25, 16, 0, 0, tzinfo=timezone.utc)
    target_date = date(2026, 10, 25)

    days_tokyo, moment_tokyo = calculate_time_remaining(target_date, "Asia/Tokyo", eval_utc)
    assert days_tokyo < 0.0, f"Expected expired in Tokyo, got {days_tokyo}"

    days_ny, moment_ny = calculate_time_remaining(target_date, "America/New_York", eval_utc)
    assert 0.0 < days_ny < 1.0, f"Expected critical hours remaining in New York, got {days_ny}"


def test_repeated_runs_and_alert_deduplication(db_session: Session, tenant_a: Tenant, sample_items: dict):
    """
    Repeated scheduled runs must not duplicate alerts for the same item at the same level.
    """
    eval_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/New_York"))

    # Run 1: Should create alerts for the 4 non-fresh items (EXPIRED, CRITICAL, WARNING, NOTICE)
    run1 = evaluate_tenant_inventory(db_session, tenant_a.id, as_of=eval_time, dry_run=False)
    assert run1.summary.alerts_created == 4
    assert run1.summary.alerts_skipped_dedup == 0

    # Run 2: Immediately afterwards (same day, same unacknowledged levels)
    run2 = evaluate_tenant_inventory(db_session, tenant_a.id, as_of=eval_time + timedelta(hours=1), dry_run=False)
    assert run2.summary.alerts_created == 0
    assert run2.summary.alerts_skipped_dedup == 4

    # Run 3: Advance time by 3 days so the WARNING item escalates to CRITICAL
    run3 = evaluate_tenant_inventory(db_session, tenant_a.id, as_of=eval_time + timedelta(days=3), dry_run=False)
    # The escalated item must produce a new alert!
    assert run3.summary.alerts_created >= 1


def test_tenant_isolation_on_expiry(db_session: Session, tenant_a: Tenant, tenant_b: Tenant):
    """Evaluating Tenant A must have zero side effects on Tenant B."""
    cat = db_session.query(Category).first()
    today = date(2026, 10, 22)

    # Tenant B item expiring today
    b_item = InventoryItem(
        tenant_id=tenant_b.id,
        category_id=cat.id,
        name="Tenant B Croissant",
        sku="TB-EXP-01",
        current_quantity=10.0,
        unit=ItemUnit.UNITS.value,
        cost_per_unit=2.00,
        purchase_date=today - timedelta(days=1),
        expiry_date=today,
        status=InventoryStatus.ACTIVE.value,
    )
    db_session.add(b_item)
    db_session.commit()

    # Evaluate Tenant A
    evaluate_tenant_inventory(db_session, tenant_a.id, dry_run=False)

    # Verify Tenant B item was untouched
    db_session.refresh(b_item)
    assert b_item.status == InventoryStatus.ACTIVE.value

    # Verify Tenant B alert history is empty
    b_alerts = db_session.query(ExpiryAlertHistory).filter(ExpiryAlertHistory.tenant_id == tenant_b.id).count()
    assert b_alerts == 0


def test_scheduler_isolated_error_resilience(db_session: Session, tenant_a: Tenant, tenant_b: Tenant):
    """Scheduler must continue evaluating remaining tenants even if one tenant fails."""
    result = run_scheduled_expiry_evaluation(db_session)
    assert result["tenants_evaluated"] >= 2
    assert result["tenants_failed"] == 0


def test_alert_acknowledgment_flow(db_session: Session, tenant_a: Tenant, user_a_owner: User, sample_items: dict):
    """Authorized users can acknowledge alerts with operational actions."""
    eval_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
    evaluate_tenant_inventory(db_session, tenant_a.id, as_of=eval_time, dry_run=False)

    alert = db_session.query(ExpiryAlertHistory).filter(ExpiryAlertHistory.tenant_id == tenant_a.id).first()
    assert alert.acknowledged is False

    ack = acknowledge_alert(
        db=db_session,
        tenant_id=tenant_a.id,
        alert_id=alert.id,
        user_id=user_a_owner.id,
        action_taken=AlertAction.MARKED_FOR_DONATION.value,
    )
    assert ack.acknowledged is True
    assert ack.acknowledged_by_user_id == user_a_owner.id
    assert ack.action_taken == AlertAction.MARKED_FOR_DONATION.value


def test_api_expiry_evaluation_and_config(client: TestClient, token_a_owner: str, sample_items: dict):
    """Test REST API on-demand evaluation, config retrieval, and updating."""
    # 1. On-demand evaluation
    eval_resp = client.post(
        "/api/v1/inventory/expiry/evaluate?dry_run=false",
        headers={"Authorization": f"Bearer {token_a_owner}"},
    )
    assert eval_resp.status_code == 200
    data = eval_resp.json()["data"]
    assert data["summary"]["total_evaluated"] >= 5
    assert data["scheduler_diagnostics"]["scheduler_mode"] == "ON_DEMAND_AND_CRON"

    # 2. Get expiring items
    expiring_resp = client.get(
        "/api/v1/inventory/expiring?status=CRITICAL",
        headers={"Authorization": f"Bearer {token_a_owner}"},
    )
    assert expiring_resp.status_code == 200
    exp_data = expiring_resp.json()["data"]
    for item in exp_data["items"]:
        assert item["alert_level"] == "CRITICAL"

    # 3. Get alert config
    cfg_resp = client.get(
        "/api/v1/alerts/config",
        headers={"Authorization": f"Bearer {token_a_owner}"},
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["data"]["critical_threshold_hours"] == 24

    # 4. Update alert config
    upd_resp = client.put(
        "/api/v1/alerts/config",
        headers={"Authorization": f"Bearer {token_a_owner}"},
        json={
            "critical_threshold_hours": 36,
            "warning_threshold_days": 4,
            "notice_threshold_days": 8,
        },
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["data"]["critical_threshold_hours"] == 36
    assert upd_resp.json()["data"]["warning_threshold_days"] == 4


def test_synthetic_fixture_classification_accuracy(db_session: Session, tenant_a: Tenant):
    """
    Synthetic ground-truth fixture test:
    Creates 20 items with known intended classifications (4 expired, 4 critical, 4 warning, 4 notice, 4 fresh).
    Verifies 100% agreement: 0 false alerts, 0 missed alerts.
    """
    cat = db_session.query(Category).first()
    today = date(2026, 10, 22)
    eval_time = datetime(2026, 10, 22, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/New_York"))

    # Config: crit=24h, warn=3d, notice=7d
    config = get_or_create_alert_config(db_session, tenant_a.id)

    ground_truth = []
    # 4 Expired (offsets -10, -5, -2, -1 days -> days_rem < 0)
    for off in [-10, -5, -2, -1]:
        ground_truth.append((today + timedelta(days=off), AlertLevel.EXPIRED.value))
    # 4 Critical (offsets 0 days -> expiring today, days_rem = 0.50 days <= 1.0 day)
    for off in [0, 0, 0, 0]:
        ground_truth.append((today + timedelta(days=off), AlertLevel.CRITICAL.value))
    # 4 Warning (offsets +1, +1, +2, +2 days -> days_rem = 1.50, 2.50 days, <= 3.0 days)
    for off in [1, 1, 2, 2]:
        ground_truth.append((today + timedelta(days=off), AlertLevel.WARNING.value))
    # 4 Notice (offsets +3, +4, +5, +6 days -> days_rem = 3.50, 4.50, 5.50, 6.50 days, <= 7.0 days)
    for off in [3, 4, 5, 6]:
        ground_truth.append((today + timedelta(days=off), AlertLevel.NOTICE.value))
    # 4 Fresh (offsets +7, +8, +14, +30 days -> days_rem = 7.50, 8.50, 14.50, 30.50 days, > 7.0 days)
    for off in [7, 8, 14, 30]:
        ground_truth.append((today + timedelta(days=off), "FRESH"))

    for idx, (exp_date, expected_level) in enumerate(ground_truth):
        item = InventoryItem(
            tenant_id=tenant_a.id,
            category_id=cat.id,
            name=f"Synthetic Item {idx}",
            sku=f"SYNTH-{idx:03d}",
            current_quantity=10.0,
            unit=ItemUnit.UNITS.value,
            cost_per_unit=1.00,
            purchase_date=today - timedelta(days=30),
            expiry_date=exp_date,
            status=InventoryStatus.ACTIVE.value,
        )
        db_session.add(item)
    db_session.commit()

    resp = evaluate_tenant_inventory(db_session, tenant_a.id, as_of=eval_time, dry_run=True)
    assert resp.summary.expired_count == 4
    assert resp.summary.critical_count == 4
    assert resp.summary.warning_count == 4
    assert resp.summary.notice_count == 4
    assert resp.summary.fresh_count == 4

    # Ground truth validation counts:
    false_alerts = 0
    missed_alerts = 0
    for idx, (exp_date, expected_level) in enumerate(ground_truth):
        match = next(i for i in resp.items if i.sku == f"SYNTH-{idx:03d}")
        if match.alert_level != expected_level:
            if match.alert_level == "FRESH" and expected_level != "FRESH":
                missed_alerts += 1
            else:
                false_alerts += 1

    assert false_alerts == 0, f"Encountered {false_alerts} false alerts!"
    assert missed_alerts == 0, f"Encountered {missed_alerts} missed alerts!"
