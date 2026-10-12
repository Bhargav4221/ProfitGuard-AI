"""Integrations API Endpoints.

Provides:
- GET  /integrations/shopify             (Get connected store status; tenant authenticated)
- POST /integrations/shopify/configure   (Configure/connect store credentials; OPERATOR, ADMIN, OWNER)
- POST /integrations/shopify/disconnect  (Disconnect store credentials; OPERATOR, ADMIN, OWNER)
- GET  /integrations/shopify/webhooks    (List webhook delivery logs; tenant authenticated)
- POST /integrations/shopify/webhook     (Public inbound Shopify webhook receiver with HMAC check)
"""

from typing import Annotated, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_tenant_context, require_role
from app.core.tenant import OrganizationRole, TenantContext
from app.models.whatsapp import WhatsAppConfig
from app.schemas.shopify import (
    ShopifyStoreConfigIn,
    ShopifyStoreConfigOut,
    ShopifyWebhookDeliveryListOut,
    ShopifyWebhookDeliveryOut,
)
from app.schemas.whatsapp import (
    WhatsAppConfigIn,
    WhatsAppConfigOut,
    WhatsAppMessageListOut,
    WhatsAppMessageOut,
    WhatsAppOptOutOut,
    WhatsAppSendNdrIn,
    WhatsAppSendOtpIn,
    WhatsAppSendTestIn,
    WhatsAppTestConnectionOut,
)
from app.services.shopify_service import ShopifyService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/integrations", tags=["Integrations"])

OPERATOR_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.OPERATOR}


@router.get("/shopify", response_model=Optional[ShopifyStoreConfigOut])
def get_shopify_configuration(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves the current Shopify store connection configuration for the active organization."""
    store = ShopifyService.get_store(tenant.org_id, session)
    if not store:
        return None

    return ShopifyStoreConfigOut(
        id=store.id,
        org_id=store.org_id,
        shop_domain=store.shop_domain,
        status=store.status,
        has_access_token=bool(store.access_token_encrypted),
        has_webhook_secret=bool(store.webhook_secret_encrypted),
        scopes=store.scopes,
        api_version=store.api_version,
        installed_at=store.installed_at,
        uninstalled_at=store.uninstalled_at,
        created_at=store.created_at,
        updated_at=store.updated_at,
    )


@router.post("/shopify/configure", response_model=ShopifyStoreConfigOut)
def configure_shopify_store(
    config_in: ShopifyStoreConfigIn,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Configures or updates merchant Shopify store credentials, encrypting sensitive tokens."""
    store = ShopifyService.configure_store(
        org_id=tenant.org_id,
        config=config_in,
        session=session,
        actor_user_id=tenant.user_id,
    )

    return ShopifyStoreConfigOut(
        id=store.id,
        org_id=store.org_id,
        shop_domain=store.shop_domain,
        status=store.status,
        has_access_token=bool(store.access_token_encrypted),
        has_webhook_secret=bool(store.webhook_secret_encrypted),
        scopes=store.scopes,
        api_version=store.api_version,
        installed_at=store.installed_at,
        uninstalled_at=store.uninstalled_at,
        created_at=store.created_at,
        updated_at=store.updated_at,
    )


@router.post("/shopify/disconnect")
def disconnect_shopify_store(
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Disconnects the connected Shopify store and revokes credentials."""
    store = ShopifyService.disconnect_store(
        org_id=tenant.org_id,
        session=session,
        actor_user_id=tenant.user_id,
    )
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No connected Shopify store found for this organization.",
        )
    return {"status": "success", "message": f"Shopify store '{store.shop_domain}' disconnected."}


@router.get("/shopify/webhooks", response_model=ShopifyWebhookDeliveryListOut)
def list_shopify_webhook_deliveries(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lists recent inbound webhook deliveries and processing statuses for audit."""
    items, total = ShopifyService.list_deliveries(
        org_id=tenant.org_id,
        session=session,
        page=page,
        page_size=page_size,
    )
    return ShopifyWebhookDeliveryListOut(
        items=[ShopifyWebhookDeliveryOut.model_validate(it) for it in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/shopify/webhook", status_code=status.HTTP_200_OK)
async def receive_shopify_webhook(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
):
    """Public webhook receiver endpoint for official Shopify webhooks.
    
    Verifies X-Shopify-Hmac-Sha256 against raw body, deduplicates via X-Shopify-Delivery-Id,
    and transitions orders through the decision engine and delivery state machine.
    """
    raw_body = await request.body()
    headers_dict = dict(request.headers)

    status_code, response_data = ShopifyService.handle_webhook(
        raw_body=raw_body,
        headers=headers_dict,
        session=session,
    )
    response.status_code = status_code
    return response_data


# =============================================================================
# Meta WhatsApp Business Cloud API Endpoints
# =============================================================================


def _map_whatsapp_config(conf: WhatsAppConfig) -> WhatsAppConfigOut:
    return WhatsAppConfigOut(
        id=conf.id,
        org_id=conf.org_id,
        phone_number_id=conf.phone_number_id,
        business_account_id=conf.business_account_id,
        has_access_token=bool(conf.access_token_encrypted),
        has_app_secret=bool(conf.app_secret_encrypted),
        webhook_verify_token=conf.webhook_verify_token,
        operating_mode=conf.operating_mode,
        status=conf.status,
        verified_name=conf.verified_name,
        quality_rating=conf.quality_rating,
        api_version=conf.api_version,
        webhook_url=conf.webhook_url,
        last_webhook_received_at=conf.last_webhook_received_at,
        last_error=conf.last_error,
        created_at=conf.created_at,
        updated_at=conf.updated_at,
    )


@router.get("/whatsapp", response_model=Optional[WhatsAppConfigOut])
def get_whatsapp_configuration(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Retrieves current WhatsApp Business Cloud API configuration for the active organization."""
    conf = WhatsAppService.get_config(tenant.org_id, session)
    if not conf:
        return None
    return _map_whatsapp_config(conf)


@router.post("/whatsapp/configure", response_model=WhatsAppConfigOut)
def configure_whatsapp(
    config_in: WhatsAppConfigIn,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Configures or updates merchant WhatsApp credentials, encrypting tokens via AES-256-GCM."""
    conf = WhatsAppService.configure_config(
        org_id=tenant.org_id,
        config_in=config_in,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return _map_whatsapp_config(conf)


@router.post("/whatsapp/disconnect")
def disconnect_whatsapp(
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Revokes WhatsApp credentials and sets integration state to DISCONNECTED."""
    conf = WhatsAppService.disconnect_config(
        org_id=tenant.org_id,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return {"status": "success", "message": "WhatsApp integration disconnected."}


@router.post("/whatsapp/test-connection", response_model=WhatsAppTestConnectionOut)
def test_whatsapp_connection(
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Diagnoses connectivity with Meta WhatsApp Cloud API (or validates mock sandbox)."""
    return WhatsAppService.test_connection(org_id=tenant.org_id, session=session)


@router.post("/whatsapp/send-test", response_model=WhatsAppMessageOut)
def send_whatsapp_test_message(
    test_in: WhatsAppSendTestIn,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Sends a test WhatsApp message to an authorized recipient phone number."""
    msg = WhatsAppService.send_message(
        org_id=tenant.org_id,
        recipient_phone=test_in.recipient_phone,
        message_type="TEXT",
        text_body=test_in.message_text,
        session=session,
        actor_user_id=tenant.user_id,
    )
    return WhatsAppMessageOut.model_validate(msg)


@router.post("/whatsapp/send-otp", response_model=WhatsAppMessageOut)
def send_whatsapp_order_otp(
    otp_in: WhatsAppSendOtpIn,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Dispatches a pre-dispatch COD OTP / Confirmation message to customer for an open order."""
    msg = WhatsAppService.send_cod_verification(
        order_id=otp_in.order_id,
        org_id=tenant.org_id,
        session=session,
        recipient_phone=otp_in.recipient_phone,
        actor_user_id=tenant.user_id,
    )
    return WhatsAppMessageOut.model_validate(msg)


@router.post("/whatsapp/send-ndr-recovery", response_model=WhatsAppMessageOut)
def send_whatsapp_ndr_recovery(
    ndr_in: WhatsAppSendNdrIn,
    tenant: Annotated[TenantContext, Depends(require_role(OPERATOR_ROLES))],
    session: Annotated[Session, Depends(get_db)],
):
    """Dispatches an NDR customer recovery message for delivery address verification / reattempt."""
    msg = WhatsAppService.send_ndr_recovery(
        ndr_case_id=ndr_in.ndr_case_id,
        org_id=tenant.org_id,
        session=session,
        recipient_phone=ndr_in.recipient_phone,
        notes=ndr_in.notes,
        actor_user_id=tenant.user_id,
    )
    return WhatsAppMessageOut.model_validate(msg)


@router.get("/whatsapp/messages", response_model=WhatsAppMessageListOut)
def list_whatsapp_messages(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order_id: Optional[UUID] = Query(None),
    ndr_case_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
):
    """Lists recent WhatsApp outbound and inbound messages, delivery receipts, and errors."""
    items, total = WhatsAppService.list_messages(
        org_id=tenant.org_id,
        session=session,
        page=page,
        page_size=page_size,
        order_id=order_id,
        ndr_case_id=ndr_case_id,
        status=status,
    )
    return WhatsAppMessageListOut(
        items=[WhatsAppMessageOut.model_validate(it) for it in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/whatsapp/opt-outs", response_model=List[WhatsAppOptOutOut])
def list_whatsapp_opt_outs(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[Session, Depends(get_db)],
):
    """Lists phone numbers registered in tenant's WhatsApp opt-out list."""
    opt_outs = WhatsAppService.list_opt_outs(org_id=tenant.org_id, session=session)
    return [WhatsAppOptOutOut.model_validate(it) for it in opt_outs]


@router.get("/whatsapp/webhook")
def verify_whatsapp_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
):
    """Official Meta Webhook GET Challenge verification endpoint.
    
    Responds to Meta challenge handshake with exact challenge value.
    """
    params = request.query_params
    hub_mode = params.get("hub.mode")
    hub_verify_token = params.get("hub.verify_token")
    hub_challenge = params.get("hub.challenge")

    challenge_val = WhatsAppService.verify_webhook_challenge(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
        session=session,
    )
    return PlainTextResponse(content=str(challenge_val), status_code=status.HTTP_200_OK)


@router.post("/whatsapp/webhook", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
):
    """Public webhook receiver endpoint for Meta WhatsApp Business Cloud API.
    
    Verifies X-Hub-Signature-256 against configured app secrets,
    deduplicates delivery updates idempotently, and updates message statuses / order workflows.
    """
    raw_body = await request.body()
    headers_dict = dict(request.headers)

    status_code, response_data = WhatsAppService.handle_webhook(
        raw_body=raw_body,
        headers=headers_dict,
        session=session,
    )
    response.status_code = status_code
    return response_data
