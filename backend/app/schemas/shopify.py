"""Pydantic Schemas for Shopify Store Configuration and Webhook Deliveries."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ShopifyStoreConfigIn(BaseModel):
    shop_domain: str = Field(..., description="Shopify store domain, e.g. 'my-brand.myshopify.com'")
    access_token: Optional[str] = Field(None, description="Shopify Admin API access token")
    webhook_secret: Optional[str] = Field(None, description="Shopify webhook HMAC signing secret")
    scopes: Optional[str] = Field("read_orders,write_orders", description="OAuth scopes")


class ShopifyStoreConfigOut(BaseModel):
    id: UUID
    org_id: UUID
    shop_domain: str
    status: str
    has_access_token: bool
    has_webhook_secret: bool
    scopes: Optional[str] = None
    api_version: str
    installed_at: Optional[datetime] = None
    uninstalled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShopifyWebhookDeliveryOut(BaseModel):
    id: UUID
    org_id: Optional[UUID] = None
    shopify_delivery_id: str
    topic: str
    shop_domain: str
    shopify_order_id: Optional[str] = None
    order_id: Optional[UUID] = None
    status: str
    error_message: Optional[str] = None
    payload_summary: Optional[Dict[str, Any]] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ShopifyWebhookDeliveryListOut(BaseModel):
    items: List[ShopifyWebhookDeliveryOut]
    total: int
    page: int
    page_size: int
