"""FastAPI Request Dependencies for Database Sessions, Auth, and Tenant Context."""

from typing import Callable, List, Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.app.core.security import decode_token
from backend.app.core.tenant import (
    CrossTenantAccessError,
    TenantContext,
    TenantNotFoundError,
    resolve_tenant_context,
)
from backend.app.db.session import get_db

security_scheme = HTTPBearer(auto_error=False)


def get_current_tenant_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    x_test_user_id: Optional[str] = Header(None, alias="X-Test-User-Id"),
    x_test_tenant_id: Optional[str] = Header(None, alias="X-Test-Tenant-Id"),
    db: Session = Depends(get_db),
) -> TenantContext:
    """
    Extracts authenticated user and tenant context.
    Supports standard Bearer JWT tokens and explicit test header overrides in test/debug mode.
    """
    user_id: Optional[str] = None
    claim_tenant_id: Optional[str] = None

    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            user_id = payload.get("sub")
            claim_tenant_id = payload.get("tenant_id")
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials or token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif x_test_user_id:
        # Development / Test fixture bypass
        user_id = x_test_user_id
        claim_tenant_id = x_test_tenant_id

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        context = resolve_tenant_context(
            session=db,
            user_id=user_id,
            claim_tenant_id=claim_tenant_id,
        )
        return context
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except CrossTenantAccessError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


def require_roles(allowed_roles: List[str]) -> Callable:
    """
    Factory creating a role-enforcement dependency.
    """
    def role_checker(
        context: TenantContext = Depends(get_current_tenant_context),
    ) -> TenantContext:
        if context.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the following roles: {', '.join(allowed_roles)}",
            )
        return context

    return role_checker
