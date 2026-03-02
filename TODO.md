# TODO — OpenTaberna API Implementation Roadmap

Ordered by dependency. Each phase builds on the previous.  
CRUD for items (`crud-item-store`) is handled by a partner and not listed here.

---

## Shared Infrastructure (already done ✅)

- [x] Config module (`shared/config/`)
- [x] Logger module (`shared/logger/`)
- [x] Exceptions module (`shared/exceptions/`)
- [x] Responses module (`shared/responses/`)
- [x] Database module (`shared/database/`) — async SQLAlchemy 2.0, BaseRepository, migrations, health
- [x] Keycloak auth (`authorize/keycloak.py`)
- [x] FastAPI app skeleton (`main.py`)

---

## Model Convention

> **All models throughout this project are pure Pydantic models.**  
> SQLAlchemy's `Base` / `DeclarativeBase` is **not used** for domain entities.  
> Database interaction happens via the `BaseRepository` with raw SQL or query builders — models are validated and serialized exclusively through Pydantic.

Pattern per entity:

```
models/
├── customer.py
│   ├── CustomerBase(BaseModel)       # shared fields
│   ├── CustomerCreate(CustomerBase)  # input / write schema
│   ├── CustomerUpdate(BaseModel)     # partial update (all Optional)
│   └── CustomerResponse(CustomerBase)  # output / read schema, incl. id + timestamps
```

- Use `model_config = ConfigDict(from_attributes=True)` on response models if mapping from DB rows
- Timestamps (`created_at`, `updated_at`) are read-only response fields, never in Create/Update schemas
- Primary keys are always in response models only, never in Create schemas

---

## Phase 0 — Domain Models & DB Schema

> Prerequisite for everything. No service can be built without these.

### 0.1 Customer & Address

- [ ] `CustomerBase`, `CustomerCreate`, `CustomerUpdate`, `CustomerResponse` — fields: id, keycloak_user_id, email, name, created_at, updated_at
- [ ] `AddressBase`, `AddressCreate`, `AddressUpdate`, `AddressResponse` — fields: id, customer_id, street, city, zip, country, is_default, created_at, updated_at
- [ ] Alembic migration for `customers` + `addresses` (schema defined separately from Pydantic models)
- [ ] `CustomerRepository(BaseRepository)` — typed to `CustomerResponse`
- [ ] `AddressRepository(BaseRepository)` — typed to `AddressResponse`

### 0.2 Inventory

> Depends on partner's `Product`/`SKU` models being accessible.

- [ ] `InventoryItemBase`, `InventoryItemCreate`, `InventoryItemUpdate`, `InventoryItemResponse` — fields: id, sku_id, on_hand, reserved, created_at, updated_at
- [ ] `StockReservationBase`, `StockReservationCreate`, `StockReservationResponse` — fields: id, inventory_item_id, order_id, quantity, expires_at, status (`ReservationStatus` enum: ACTIVE / COMMITTED / EXPIRED / RELEASED), created_at, updated_at
- [ ] DB constraint (in migration): `on_hand >= 0`, `reserved >= 0`, `on_hand >= reserved`
- [ ] Alembic migration for `inventory_items` + `stock_reservations`
- [ ] `InventoryRepository(BaseRepository)`
- [ ] `StockReservationRepository(BaseRepository)`

### 0.3 Order & OrderItem

- [ ] `OrderStatus` enum: `DRAFT` → `PENDING_PAYMENT` → `PAID` → `READY_TO_SHIP` → `SHIPPED` → `CANCELLED`
- [ ] `OrderBase`, `OrderCreate`, `OrderUpdate`, `OrderResponse` — fields: id, customer_id, status, total_amount, currency, deleted_at, created_at, updated_at
- [ ] `OrderItemBase`, `OrderItemCreate`, `OrderItemResponse` — fields: id, order_id, sku_id, quantity, unit_price (price snapshot at order time), created_at, updated_at
- [ ] Alembic migration for `orders` + `order_items`
- [ ] `OrderRepository(BaseRepository)`
- [ ] `OrderItemRepository(BaseRepository)`

### 0.4 Payment

- [ ] `PaymentStatus` enum: PENDING / SUCCEEDED / FAILED / REFUNDED
- [ ] `PaymentProvider` enum: STRIPE / …
- [ ] `PaymentBase`, `PaymentCreate`, `PaymentUpdate`, `PaymentResponse` — fields: id, order_id, provider, provider_reference, amount, currency, status, created_at, updated_at
- [ ] Alembic migration for `payments` (unique constraint on `order_id`, unique on `provider_reference`)
- [ ] `PaymentRepository(BaseRepository)`

### 0.5 Webhook Event Inbox (idempotency)

- [ ] `WebhookEventCreate`, `WebhookEventResponse` — fields: id, provider, event_id, payload (dict), processed_at, created_at
- [ ] Alembic migration for `webhook_events` (unique constraint on `(provider, event_id)`)
- [ ] `WebhookEventRepository(BaseRepository)`

### 0.6 Shipment

- [ ] `Carrier` enum: DHL / MANUAL
- [ ] `ShipmentStatus` enum: PENDING / LABEL_CREATED / HANDED_OVER
- [ ] `ShipmentBase`, `ShipmentCreate`, `ShipmentUpdate`, `ShipmentResponse` — fields: id, order_id, carrier, tracking_number, label_url, label_format (PDF / ZPL), status, created_at, updated_at
- [ ] Alembic migration for `shipments` (unique constraint on `order_id`)
- [ ] `ShipmentRepository(BaseRepository)`

---

## Phase 1 — Checkout & Payment (`services/order-processing/`)

> Create service: `src/app/services/order-processing/`

### 1.1 Cart / Draft Order API

- [ ] `POST /orders` — create draft order with line items (price snapshot from SKU)
- [ ] `GET /orders/{id}` — retrieve order (customer-scoped via Keycloak token)
- [ ] `DELETE /orders/{id}` — cancel draft order
- [ ] Pydantic models: `OrderCreate`, `OrderItemCreate`, `OrderResponse`, `OrderDetailResponse`
- [ ] Business logic: validate SKUs exist, calculate totals, create `Order` in `DRAFT` status
- [ ] Register router in `main.py`

### 1.2 Inventory Reservation

- [ ] `functions/reserve_inventory.py` — atomic check-and-reserve (single DB transaction)
  - Check `on_hand - reserved >= requested quantity`
  - Insert `StockReservation` (status=ACTIVE, expires_at = now + configurable TTL)
  - Increment `reserved` on `InventoryItem`
- [ ] `functions/release_reservation.py` — set reservation to RELEASED, decrement `reserved`
- [ ] `functions/commit_reservation.py` — set reservation to COMMITTED, decrement `on_hand` + `reserved`
- [ ] `functions/expire_reservations.py` — background cleanup: expire stale reservations and release stock
- [ ] Add `RESERVATION_TTL_MINUTES` to `Settings`

### 1.3 Checkout Endpoint

- [ ] `POST /orders/{id}/checkout` — transition `DRAFT` → `PENDING_PAYMENT`
  - Reserve inventory (reject with 409 if insufficient stock, include which SKUs)
  - Create PSP payment session/intent (see 1.4)
  - Return PSP client secret / redirect URL

### 1.4 PSP Integration (Stripe recommended as first adapter)

- [ ] `services/payment_provider/` subfolder inside `order-processing`
- [ ] `PaymentProviderAdapter` interface (abstract base): `create_session(order) → ProviderSession`, `verify_webhook(headers, body) → WebhookPayload`
- [ ] `StripeAdapter` implementing the interface
- [ ] Add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` to `Settings`

### 1.5 Webhook Endpoint

- [ ] `POST /webhooks/stripe` — raw body endpoint (do NOT parse body as JSON before signature check)
- [ ] Signature verification via `StripeAdapter.verify_webhook()`
- [ ] Idempotency check: lookup `(provider="stripe", event_id=stripe_event_id)` in `webhook_events` — return 200 if already processed
- [ ] On `payment_intent.succeeded`:
  - DB transaction: insert `WebhookEvent`, update `Payment` → SUCCEEDED, update `Order` → PAID, call `commit_reservation()`
  - Enqueue fulfillment job (Phase 3; use a no-op stub for now)
- [ ] On `payment_intent.payment_failed`:
  - DB transaction: insert `WebhookEvent`, update `Payment` → FAILED, update `Order` → CANCELLED, call `release_reservation()`
- [ ] Register webhook router in `main.py`

---

## Phase 2 — Admin Fulfillment (`services/admin/`)

> Requires Phase 1 complete. No carrier integration yet — ship manually.

- [ ] Create service: `src/app/services/admin/`
- [ ] Keycloak role guard for all admin routes (e.g. `role="admin"`)

### 2.1 Admin Order Management

- [ ] `GET /admin/orders` — list orders, filter by status, paginated (`PaginatedResponse`)
- [ ] `GET /admin/orders/{id}` — order detail with items, customer, address, payment, shipment
- [ ] `PATCH /admin/orders/{id}/status` — manual status override with audit log

### 2.2 Pick & Pack Documents

- [ ] `GET /admin/orders/{id}/packing-slip` — HTML response (print-friendly) listing items, quantities, customer address
- [ ] `GET /admin/orders/{id}/pick-list` — aggregate pick list across multiple orders (batch picking)

### 2.3 Manual Shipment Marking

- [ ] `POST /admin/orders/{id}/shipments` — create `Shipment` with manual tracking number; transition `Order` → `READY_TO_SHIP`
- [ ] `POST /admin/orders/{id}/ship` — mark as handed over to carrier; transition `Order` → `SHIPPED`
- [ ] Trigger customer notification email on `SHIPPED` (see 2.4)

### 2.4 Customer Notification Email

- [ ] `functions/send_tracking_email.py` — send tracking number + carrier link to customer
- [ ] Add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` to `Settings`
- [ ] Use async SMTP (e.g. `aiosmtplib`); templated HTML email

---

## Phase 3 — Automated Label Generation (`services/fulfillment/`)

> Requires Phase 2 complete. Replaces the manual shipping step with automation.

### 3.1 Background Job System

- [ ] Evaluate and add queue backend: **ARQ** (Redis-based, async, fits FastAPI well) recommended
- [ ] Add `REDIS_URL` to `Settings`
- [ ] Worker entry point: `src/app/worker.py`
- [ ] Job: `create_label_job(order_id: int)` — retries (max 5), exponential backoff, dead-letter logging

### 3.2 Carrier Abstraction Layer

- [ ] `services/fulfillment/carrier/interface.py` — `CarrierAdapter` abstract base
  ```
  create_label(order: OrderResponse, shipment: ShipmentResponse) → LabelResult
  LabelResult(BaseModel): tracking_number, label_url, label_format
  ```
- [ ] `ManualCarrierAdapter` — no-op adapter (used in Phase 2, keeps interface consistent)

### 3.3 DHL Adapter

- [ ] `services/fulfillment/carrier/dhl.py` — `DhlAdapter(CarrierAdapter)`
- [ ] DHL Parcel DE Shipping API (REST): create shipment, retrieve label PDF/ZPL
- [ ] Add `DHL_API_KEY`, `DHL_ACCOUNT_NUMBER`, `DHL_PRODUCT` to `Settings`
- [ ] Store label binary in object storage (S3 / MinIO) — add `STORAGE_*` settings
- [ ] Handle DHL error responses with proper `AppException` subclass

### 3.4 Admin Label Workflow

- [ ] `POST /admin/orders/{id}/label` — trigger `create_label_job` manually (or re-trigger on failure)
- [ ] `GET /admin/orders/{id}/label` — download label PDF/ZPL (proxy from storage)
- [ ] Rules: only allowed when `Order.status == PAID` and no committed label exists

### 3.5 Outbox Pattern (reliable job enqueueing)

- [ ] `OutboxEventCreate`, `OutboxEventResponse` Pydantic models — fields: id, event_type, payload (dict), enqueued_at, created_at
- [ ] Replace direct ARQ enqueue in webhook handler with outbox insert (same transaction as order update)
- [ ] Background poller: read un-enqueued outbox events, push to ARQ, mark enqueued

---

## Phase 4 — Operational Hardening

### 4.1 Observability

- [ ] Correlation ID middleware — inject `X-Request-ID` into every request's log context (already supported by `shared/logger/context.py`)
- [ ] Structured log fields: `order_id`, `payment_id`, `user_id` on all relevant log statements
- [ ] Health endpoints: `GET /health` (liveness) + `GET /health/ready` (DB + Redis checks via `shared/database/health.py`)
- [ ] Prometheus metrics endpoint (optional; add `prometheus-fastapi-instrumentator`)

### 4.2 Reservation Expiry Job (production-grade)

- [ ] ARQ scheduled job: run `expire_reservations()` every N minutes
- [ ] Alert admin on repeated expiry failures

### 4.3 Payment Reversals / Refunds

- [ ] Handle `charge.refunded` / `payment_intent.canceled` Stripe webhooks
- [ ] `Payment` → REFUNDED, `Order` → CANCELLED, `release_reservation()` if not yet committed
- [ ] If already committed/shipped: create `Refund` record (separate model), flag for manual review

### 4.4 Returns & RMA (basic)

- [ ] `ReturnStatus` enum: REQUESTED / APPROVED / RECEIVED / REFUNDED
- [ ] `ReturnCreate`, `ReturnUpdate`, `ReturnResponse` Pydantic models — fields: id, order_id, reason, status, created_at, updated_at
- [ ] `POST /orders/{id}/returns` — customer requests return
- [ ] `PATCH /admin/returns/{id}` — admin approves and processes

### 4.5 Security Hardening

- [ ] Restrict CORS `origins` in `main.py` (currently `["*"]`)
- [ ] Rate limiting on webhook endpoint (e.g. `slowapi`)
- [ ] Replace `secret_key` default `"CHANGE_ME_IN_PRODUCTION"` with startup validation

---

## Cross-Cutting Tasks (do as you go)

- [ ] Write pytest tests for every new service module (mirror `tests/` structure)
- [ ] Add each new model to Alembic `env.py` imports so auto-generate works
- [ ] Register every new service router in `main.py`
- [ ] Keep `Settings` as the single source of truth for all env vars — no hardcoded values
- [ ] Use `shared/exceptions/` for all error cases — never return raw HTTP exceptions from business logic
- [ ] Use `shared/responses/` factory helpers (`success()`, `paginated()`, `error_from_exception()`) in all routers
