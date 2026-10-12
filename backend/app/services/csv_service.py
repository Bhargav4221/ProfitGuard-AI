"""Robust Streaming CSV Ingestion Service for Indian D2C Merchant Exports.

Features:
- Handles UTF-8 and UTF-8 with BOM (utf-8-sig).
- Handles quoted fields, embedded commas, and standard RFC 4180 CSV syntax.
- Row-level validation using Decimal arithmetic, Indian mobile format, and 6-digit pincode checks.
- Two-Stage Workflow:
  Stage A (Preview): Validates and stages parsed rows without writing to orders table.
  Stage B (Commit): Transactional, idempotent write with duplicate prevention and audit logging.
- Defends against unbounded memory consumption with strict file size and row count limits.
"""

import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Set, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, ImportJobError
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.csv_import import CSVPreviewResponse, CSVRowError
from app.schemas.order import normalize_indian_phone, normalize_indian_pincode
from app.services.audit_service import AuditService

# Operational Limits
MAX_CSV_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CSV_ROWS = 5000

CSV_TEMPLATE_HEADERS = [
    "external_order_id",
    "order_date",
    "order_value",
    "payment_method",
    "customer_name",
    "customer_phone",
    "customer_email",
    "shipping_address1",
    "shipping_address2",
    "shipping_city",
    "shipping_state",
    "shipping_pincode",
    "courier_name",
    "tracking_number",
    "sku",
    "product_name",
    "quantity",
    "unit_price",
    "unit_cost",
]

CSV_TEMPLATE_SAMPLE_ROW = (
    "ORD-1001,2026-10-11T14:30:00Z,999.00,COD,Aarav Patel,9876543210,aarav@example.com,"
    "Flat 402 Lakeview Apts,MG Road,Bengaluru,Karnataka,560001,Delhivery,DEL123456789,"
    "SKU-COT-01,Organic Cotton T-Shirt,1,999.00,300.00\n"
)


class CSVService:
    @staticmethod
    def get_template() -> str:
        """Returns standard CSV template header and sample row."""
        return ",".join(CSV_TEMPLATE_HEADERS) + "\n" + CSV_TEMPLATE_SAMPLE_ROW

    @staticmethod
    def preview_csv(
        file_bytes: bytes,
        filename: str,
        org_id: UUID,
        user_id: UUID,
        session: Session,
    ) -> CSVPreviewResponse:
        """Stage A — Parses and validates CSV content without persisting orders.
        
        Stages valid rows and records row errors in an ImportJob record.
        """
        if len(file_bytes) > MAX_CSV_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"CSV file exceeds maximum allowed size of {MAX_CSV_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
            )

        try:
            # Decode using utf-8-sig to cleanly strip optional byte order mark (BOM)
            text_content = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not valid UTF-8 text.",
            )

        reader = csv.DictReader(io.StringIO(text_content))
        if not reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file is empty or missing headers.",
            )

        # Normalize header keys to lowercase stripped strings
        header_map = {orig: orig.strip().lower() for orig in reader.fieldnames if orig}
        normalized_headers = set(header_map.values())

        # Check required fields
        required_headers = {"external_order_id", "order_value", "payment_method"}
        missing_headers = required_headers - normalized_headers
        if missing_headers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV missing mandatory headers: {', '.join(sorted(missing_headers))}.",
            )

        # Create Staging ImportJob
        import_job = ImportJob(
            org_id=org_id,
            created_by_user_id=user_id,
            filename=filename,
            status="PREVIEW",
        )
        session.add(import_job)
        session.flush()

        row_errors: List[CSVRowError] = []
        parsed_orders: Dict[str, Dict[str, Any]] = {}
        file_seen_order_ids: Set[str] = set()
        duplicate_count = 0
        total_rows = 0

        # Pre-fetch existing external_order_ids for this tenant to catch duplicates early
        existing_order_ids = set(
            session.scalars(select(Order.external_order_id).where(Order.org_id == org_id)).all()
        )

        for row_idx, raw_row in enumerate(reader, start=2):  # row 1 is header
            total_rows += 1
            if total_rows > MAX_CSV_ROWS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"CSV row count exceeds maximum limit of {MAX_CSV_ROWS} rows.",
                )

            # Map raw row keys to normalized keys
            row = {header_map[k]: (v.strip() if v else "") for k, v in raw_row.items() if k in header_map}

            ext_id = row.get("external_order_id", "").strip()
            if not ext_id:
                row_errors.append(CSVRowError(
                    row_index=row_idx,
                    column_name="external_order_id",
                    error_message="external_order_id is required and cannot be blank.",
                ))
                continue

            # Check if this external order ID already exists in the tenant's database
            if ext_id in existing_order_ids:
                row_errors.append(CSVRowError(
                    row_index=row_idx,
                    external_order_id=ext_id,
                    column_name="external_order_id",
                    error_message=f"Order ID '{ext_id}' already exists in your account.",
                ))
                duplicate_count += 1
                continue

            # Check for duplicate order ID within this single CSV file (if previous row had error)
            if ext_id in file_seen_order_ids and ext_id not in parsed_orders:
                duplicate_count += 1
                row_errors.append(CSVRowError(
                    row_index=row_idx,
                    external_order_id=ext_id,
                    column_name="external_order_id",
                    error_message=f"Duplicate order ID '{ext_id}' within upload.",
                ))
                continue

            # Validate order_value
            raw_val = row.get("order_value", "").strip()
            try:
                order_value = Decimal(raw_val)
                if not order_value.is_finite() or order_value <= 0:
                    raise ValueError("order_value must be a finite positive number.")
            except (InvalidOperation, ValueError):
                file_seen_order_ids.add(ext_id)
                row_errors.append(CSVRowError(
                    row_index=row_idx,
                    external_order_id=ext_id,
                    column_name="order_value",
                    error_message=f"Invalid monetary order_value '{raw_val}'. Must be a positive decimal.",
                ))
                continue

            # Validate payment_method
            raw_pm = row.get("payment_method", "").strip().upper()
            if raw_pm not in {"COD", "PREPAID"}:
                file_seen_order_ids.add(ext_id)
                row_errors.append(CSVRowError(
                    row_index=row_idx,
                    external_order_id=ext_id,
                    column_name="payment_method",
                    error_message=f"Invalid payment_method '{raw_pm}'. Must be 'COD' or 'PREPAID'.",
                ))
                continue

            # Validate phone (if provided)
            raw_phone = row.get("customer_phone", "").strip()
            valid_phone = None
            if raw_phone:
                try:
                    valid_phone = normalize_indian_phone(raw_phone)
                except ValueError as e:
                    file_seen_order_ids.add(ext_id)
                    row_errors.append(CSVRowError(
                        row_index=row_idx,
                        external_order_id=ext_id,
                        column_name="customer_phone",
                        error_message=str(e),
                    ))
                    continue

            # Validate pincode (if provided)
            raw_pincode = row.get("shipping_pincode", "").strip()
            valid_pincode = None
            if raw_pincode:
                try:
                    valid_pincode = normalize_indian_pincode(raw_pincode)
                except ValueError as e:
                    file_seen_order_ids.add(ext_id)
                    row_errors.append(CSVRowError(
                        row_index=row_idx,
                        external_order_id=ext_id,
                        column_name="shipping_pincode",
                        error_message=str(e),
                    ))
                    continue

            # Parse order_date
            raw_date = row.get("order_date", "").strip()
            order_date_iso = datetime.now(timezone.utc).isoformat()
            if raw_date:
                try:
                    # Support ISO format or standard date format
                    dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    order_date_iso = dt.isoformat()
                except Exception:
                    file_seen_order_ids.add(ext_id)
                    row_errors.append(CSVRowError(
                        row_index=row_idx,
                        external_order_id=ext_id,
                        column_name="order_date",
                        error_message=f"Malformed order_date '{raw_date}'. Expected ISO format (e.g., 2026-10-11T14:30:00Z).",
                    ))
                    continue

            # Parse optional item info
            item_name = row.get("product_name", "").strip()
            raw_qty = row.get("quantity", "1").strip()
            raw_price = row.get("unit_price", str(order_value)).strip()
            raw_cost = row.get("unit_cost", "").strip()

            line_item = None
            if item_name:
                try:
                    qty = int(raw_qty)
                    if qty < 1:
                        raise ValueError("quantity must be at least 1")
                    u_price = Decimal(raw_price)
                    if u_price < 0 or not u_price.is_finite():
                        raise ValueError("unit_price cannot be negative")
                    u_cost = Decimal(raw_cost) if raw_cost else None
                    if u_cost is not None and (u_cost < 0 or not u_cost.is_finite()):
                        raise ValueError("unit_cost cannot be negative")

                    line_item = {
                        "product_name": item_name,
                        "sku": row.get("sku", "").strip() or None,
                        "quantity": qty,
                        "unit_price": str(u_price),
                        "unit_cost": str(u_cost) if u_cost is not None else None,
                        "total_price": str(qty * u_price),
                    }
                except (ValueError, InvalidOperation) as e:
                    file_seen_order_ids.add(ext_id)
                    row_errors.append(CSVRowError(
                        row_index=row_idx,
                        external_order_id=ext_id,
                        column_name="line_items",
                        error_message=f"Invalid line item data: {str(e)}",
                    ))
                    continue

            # Group multi-item rows under the same external order ID or detect conflict
            if ext_id in parsed_orders:
                existing_entry = parsed_orders[ext_id]
                if (
                    existing_entry["payment_method"] != raw_pm
                    or Decimal(existing_entry["order_value"]) != order_value
                    or not line_item
                ):
                    duplicate_count += 1
                    row_errors.append(CSVRowError(
                        row_index=row_idx,
                        external_order_id=ext_id,
                        column_name="external_order_id",
                        error_message=f"Duplicate order ID '{ext_id}' with conflicting attributes or without distinct line items.",
                    ))
                    continue
                else:
                    existing_entry["items"].append(line_item)
            else:
                file_seen_order_ids.add(ext_id)
                order_dict = {
                    "external_order_id": ext_id,
                    "order_date": order_date_iso,
                    "order_value": str(order_value),
                    "payment_method": raw_pm,
                    "currency": "INR",
                    "status": "PENDING",
                    "fulfillment_status": "UNFULFILLED",
                    "customer_name": row.get("customer_name", "").strip() or None,
                    "customer_phone": valid_phone,
                    "customer_email": row.get("customer_email", "").strip() or None,
                    "shipping_address1": row.get("shipping_address1", "").strip() or None,
                    "shipping_address2": row.get("shipping_address2", "").strip() or None,
                    "shipping_city": row.get("shipping_city", "").strip() or None,
                    "shipping_state": row.get("shipping_state", "").strip() or None,
                    "shipping_pincode": valid_pincode,
                    "shipping_country": "IN",
                    "courier_name": row.get("courier_name", "").strip() or None,
                    "tracking_number": row.get("tracking_number", "").strip() or None,
                    "source_channel": "CSV",
                    "items": [line_item] if line_item else [],
                }
                parsed_orders[ext_id] = order_dict

        # Save errors to ImportJobError table
        for err in row_errors:
            error_record = ImportJobError(
                org_id=org_id,
                import_job_id=import_job.id,
                row_index=err.row_index,
                external_order_id=err.external_order_id,
                column_name=err.column_name,
                error_message=err.error_message,
            )
            session.add(error_record)

        valid_orders_list = list(parsed_orders.values())

        # Update import_job metadata and stage data
        import_job.total_rows = total_rows
        import_job.valid_rows = len(valid_orders_list)
        import_job.invalid_rows = len(row_errors)
        import_job.duplicate_rows = duplicate_count
        import_job.staged_data = valid_orders_list

        session.commit()

        return CSVPreviewResponse(
            preview_id=import_job.id,
            filename=filename,
            total_rows=total_rows,
            valid_rows=len(valid_orders_list),
            invalid_rows=len(row_errors),
            duplicate_rows=duplicate_count,
            sample_valid_rows=valid_orders_list[:5],
            errors=row_errors[:100],  # Return up to first 100 errors in response preview
        )

    @staticmethod
    def commit_import(
        preview_id: UUID,
        org_id: UUID,
        user_id: UUID,
        session: Session,
    ) -> Tuple[int, int]:
        """Stage B — Atomically commits staged orders to database with idempotency."""
        import_job = session.scalar(
            select(ImportJob).where(
                ImportJob.id == preview_id,
                ImportJob.org_id == org_id,
            )
        )
        if not import_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import preview not found or unauthorized.",
            )

        if import_job.status == "COMMITTED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This import batch has already been committed.",
            )

        staged_orders = import_job.staged_data or []
        if not staged_orders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid staged orders to commit in this batch.",
            )

        # Re-verify external_order_id duplicates in DB right before insert
        staged_ids = [o["external_order_id"] for o in staged_orders]
        existing_in_db = set(
            session.scalars(
                select(Order.external_order_id).where(
                    Order.org_id == org_id,
                    Order.external_order_id.in_(staged_ids),
                )
            ).all()
        )

        inserted_count = 0
        skipped_count = 0

        for o_dict in staged_orders:
            ext_id = o_dict["external_order_id"]
            if ext_id in existing_in_db:
                skipped_count += 1
                continue

            order = Order(
                org_id=org_id,
                external_order_id=ext_id,
                order_date=datetime.fromisoformat(o_dict["order_date"]),
                currency=o_dict["currency"],
                order_value=Decimal(o_dict["order_value"]),
                payment_method=o_dict["payment_method"],
                status=o_dict["status"],
                fulfillment_status=o_dict["fulfillment_status"],
                customer_name=o_dict["customer_name"],
                customer_phone=o_dict["customer_phone"],
                customer_email=o_dict["customer_email"],
                shipping_address1=o_dict["shipping_address1"],
                shipping_address2=o_dict["shipping_address2"],
                shipping_city=o_dict["shipping_city"],
                shipping_state=o_dict["shipping_state"],
                shipping_pincode=o_dict["shipping_pincode"],
                shipping_country=o_dict["shipping_country"],
                courier_name=o_dict["courier_name"],
                tracking_number=o_dict["tracking_number"],
                source_channel="CSV",
                import_job_id=import_job.id,
            )
            session.add(order)
            session.flush()

            for item_dict in o_dict.get("items", []):
                item = OrderItem(
                    org_id=org_id,
                    order_id=order.id,
                    sku=item_dict.get("sku"),
                    product_name=item_dict["product_name"],
                    quantity=int(item_dict["quantity"]),
                    unit_price=Decimal(item_dict["unit_price"]),
                    unit_cost=Decimal(item_dict["unit_cost"]) if item_dict.get("unit_cost") else None,
                    total_price=Decimal(item_dict["total_price"]),
                )
                session.add(item)

            inserted_count += 1
            existing_in_db.add(ext_id)

        # Mark job COMMITTED
        import_job.status = "COMMITTED"
        import_job.committed_at = datetime.now(timezone.utc)

        # Record audit log
        AuditService.record_event(
            session=session,
            org_id=org_id,
            actor_user_id=user_id,
            action="CSV_IMPORT_COMMITTED",
            resource_type="ImportJob",
            resource_id=str(import_job.id),
            payload={
                "filename": import_job.filename,
                "inserted_count": inserted_count,
                "skipped_count": skipped_count,
            },
        )

        session.commit()
        return inserted_count, skipped_count
