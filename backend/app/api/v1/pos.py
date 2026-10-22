"""
Point-of-Sale (POS) API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_tenant_context, require_roles
from backend.app.core.tenant import TenantContext
from backend.app.db.session import get_db
from backend.app.models.pos import PosIntegration
from backend.app.models.user import UserRole
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.pos import (
    PosIntegrationCreate,
    PosIntegrationResponse,
    PosSyncRequest,
    PosSyncResponse,
    PosWebhookPayload,
    PosWebhookResponse,
)
from backend.app.services.pos_adapter import (
    InvalidSignatureError,
    create_pos_integration,
    get_pos_adapter,
    sync_pos_integration,
)

router = APIRouter(prefix="/pos", tags=["pos-integrations"])


def build_webhook_url(slug: str) -> str:
    """Helper to assemble webhook endpoint URL."""
    return f"https://api.foodwasteplatform.example/api/v1/pos/webhook/{slug}"


@router.post(
    "/integrations",
    response_model=SuccessEnvelope[PosIntegrationResponse],
    status_code=status.HTTP_201_CREATED,
)
def register_pos_integration(
    payload: PosIntegrationCreate,
    context: TenantContext = Depends(require_roles([UserRole.BUSINESS_OWNER.value])),
    db: Session = Depends(get_db),
):
    """
    Configure a new POS provider adapter (Square, Clover, or Mock POS).
    The webhook_signing_secret is returned only once upon creation.
    """
    integration, plaintext_secret = create_pos_integration(
        db=db,
        tenant_id=context.tenant_id,
        payload=payload,
    )
    
    resp_data = PosIntegrationResponse(
        id=integration.id,
        tenant_id=integration.tenant_id,
        provider=integration.provider,
        integration_name=integration.integration_name,
        webhook_slug=integration.webhook_slug,
        webhook_url=build_webhook_url(integration.webhook_slug),
        webhook_signing_secret=plaintext_secret,
        is_active=integration.is_active,
        last_sync_at=integration.last_sync_at,
        last_error_message=integration.last_error_message,
        created_at=integration.created_at,
    )
    return SuccessEnvelope(data=resp_data)


@router.get(
    "/integrations",
    response_model=SuccessEnvelope[List[PosIntegrationResponse]],
)
def list_pos_integrations(
    context: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    """List all registered POS provider adapters for this tenant."""
    integrations = (
        db.query(PosIntegration)
        .filter(PosIntegration.tenant_id == context.tenant_id)
        .all()
    )

    results = [
        PosIntegrationResponse(
            id=i.id,
            tenant_id=i.tenant_id,
            provider=i.provider,
            integration_name=i.integration_name,
            webhook_slug=i.webhook_slug,
            webhook_url=build_webhook_url(i.webhook_slug),
            webhook_signing_secret=None,  # Never leak signing secret on list
            is_active=i.is_active,
            last_sync_at=i.last_sync_at,
            last_error_message=i.last_error_message,
            created_at=i.created_at,
        )
        for i in integrations
    ]
    return SuccessEnvelope(data=results)


@router.post(
    "/integrations/{integration_id}/sync",
    response_model=SuccessEnvelope[PosSyncResponse],
)
def trigger_pos_sync(
    integration_id: str,
    payload: PosSyncRequest = PosSyncRequest(),
    context: TenantContext = Depends(require_roles([UserRole.BUSINESS_OWNER.value, UserRole.INVENTORY_STAFF.value])),
    db: Session = Depends(get_db),
):
    """Trigger an on-demand inventory catalog sync from external POS."""
    try:
        result = sync_pos_integration(
            db=db,
            integration_id=integration_id,
            tenant_id=context.tenant_id,
            since=payload.since,
            cursor=payload.cursor,
        )
        return SuccessEnvelope(data=result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Sync failed: {str(e)}")


@router.post(
    "/webhook/{slug}",
    response_model=PosWebhookResponse,
)
async def receive_pos_webhook(
    slug: str,
    request: Request,
    x_pos_signature: Optional[str] = Header(None, alias="X-POS-Signature"),
    db: Session = Depends(get_db),
):
    """
    Public webhook receiver for external POS transaction feeds.
    Verifies HMAC signature against stored webhook secret hash.
    """
    integration = (
        db.query(PosIntegration)
        .filter(PosIntegration.webhook_slug == slug, PosIntegration.is_active == True)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found or inactive")

    raw_body = await request.body()
    try:
        body_json = await request.json()
        payload = PosWebhookPayload.model_validate(body_json)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed webhook payload: {str(e)}")

    adapter = get_pos_adapter(integration.provider)
    try:
        result = adapter.process_webhook(
            db=db,
            integration=integration,
            payload=payload,
            raw_body=raw_body,
            signature=x_pos_signature,
            raw_secret=None,  # Mock adapter permits simulation; production validates signature
        )
        return result
    except InvalidSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Webhook processing error: {str(e)}")
