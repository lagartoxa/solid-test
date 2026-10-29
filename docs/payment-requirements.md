# Task requirements: Payment Endpoint

## Context
The project structure is done and merged: models, repositories, Alembic, `flask seed`, Swagger at `/docs`, and pytest. This document turns instructions.md and quick-start.sql into the agreed requirements for the payment part, with the decisions made with the user. The one remaining topic is how the mock provider decides success or failure, which will be discussed together with the tests. The decisions marked **[README]** must be written in the README's assumptions/decisions.

## 1. Explicit requirements (instructions.md)
| # | Requirement | Status |
|---|---|---|
| R1 | SQL schema for the payment part, added as a **new migration** | Done |
| R2 | HTTP endpoint that **starts** the payment for a cart | Done |
| R3 | Python + Flask + SQLAlchemy + PostgreSQL on the quick-start schema | Done |
| R4 | Mock payment provider that can succeed or fail | Done (by card token, see §6) |
| R5 | Tests for the endpoint | Done: every edge case |
| R6 | Git repo + README on how to run the code and the tests | Done |
| R7 | Assumptions written in the README | Ongoing |

Quality bar: no bugs, clean code and naming, DRY, KISS, every line explainable.

**Already exists, don't build:** users, carts/cart items, the payment total calculation service (external), and the user's card token (`user_payment_methods.provider_token`).

## 2. API
- `POST /carts/<cart_id>/payments` starts a payment. It returns **202 Accepted** with the `pending` payment.
  - Header `User-Id` (required) identifies the caller (no underscore: some servers, like nginx and gunicorn, drop headers with underscores). **[README]** In a real system this would be an auth token; here that felt like overkill.
  - **No `Idempotency-Key`. [README]** It is not in the task, and duplicate requests (double click, network retry) are already blocked by the "one pending/succeeded payment per cart" rule: a duplicate gets 409 and the client can GET the payment's status, so no double charge is possible. A real system whose clients retry automatically would add an `Idempotency-Key`, so a retry gets the original response instead of 409.
  - Body `payment_method_id` (**required**). **[README]** The API never picks a payment method on its own, because that is too critical; the UI decides which one is sent.
- `GET /carts/<cart_id>/payments/<payment_id>`: the client polls this for the status.
- `POST /payments/webhook`: the (mocked) provider reports `succeeded`/`failed`, with the provider transaction id and a failure reason.
  - **Signed with a shared secret** (HMAC of the body, secret from config); missing or wrong signature → **401**. **[README]**
  - A notification for a payment that is no longer `pending` (repeated or late) → **409**. **[README]** To evaluate in real life: if providers resend notifications often, answer 200 for a repeated notification with the same status.
- Everything is documented in Swagger (flask-openapi3 + Pydantic schemas).
- Flowcharts: [docs/diagrams/](diagrams/) (PlantUML).

## 3. Business rules (POST)
| Situation | Response |
|---|---|
| Cart not found, soft-deleted, or not owned by `user_id`; user not found/deleted | 404 |
| Invalid input (bad UUID, missing header/body field) | 422 |
| User has no payment method, or the given method is missing/deleted/not the user's | 409 **[README]** |
| Cart not `active` (`checked_out`/`abandoned`) | 409 |
| A `pending` or `succeeded` payment already exists for the cart | 409 |
| Empty cart | 409 |
| Cart has a soft-deleted product | 409 |
| Products in different currencies | 409 **[README]**: chosen because it doesn't seem to happen in real life (one card charge = one currency), but it would be discussed with the customer first |
| Not enough stock for any item | 409 |
| Valid | 202, payment `pending` |
| Valid, but the provider refuses the charge at the start (e.g. invalid card token) | 402: payment `failed` with the reason, reserved stock given back, cart stays `active` (the user can retry with another method) |
| Valid, but the provider is unreachable, times out or answers with an error | 502: payment `failed` with the reason, reserved stock given back, cart stays `active` (the user can retry later). 502, not 409: the request and the data were fine, a service we depend on failed |

- **Amount:** the total calculation service (interface + stub) returns line items (`quantity`, `unit_price`). Our code sums them into `amount`. The currency comes from the cart's products.
- **Stock is reserved at POST:** `stock_quantity` is reduced when the payment starts and given back if the payment fails.
- **Concurrency:** the cart row (and the product rows, for stock) are locked with `SELECT … FOR UPDATE`, plus a partial unique index on `payments.cart_id WHERE status IN ('pending','succeeded')`.

## 4. Webhook rules
- `succeeded`: payment → `succeeded`, cart → `checked_out`, store the provider transaction id.
- `failed`: payment → `failed` with the failure reason, reserved stock is given back, the cart stays `active` so the user can retry.
- Only a `pending` payment can change status.

- **Cart history:** `carts` is versioned (see [versioned-tables-plan.md](versioned-tables-plan.md)), so every status change made by the payment flow is recorded automatically. Concurrent updates of the same cart raise `StaleDataError`, which the payment flow must handle (on top of the row lock).

- **Logging:** the calls to the payment provider mock and to the total calculation service must go through `action_logger.external_call(...)`, so the payloads sent and received are logged. Data changes go through the repositories, which log them (see the Logging rules in CLAUDE.md).

## 5. Schema: `payments` table (new Alembic migration)
`BaseModel` columns (id, created_at, updated_at, deleted_at), plus `cart_id` FK, `user_id` FK, `payment_method_id` FK, `amount NUMERIC(12,2) CHECK > 0`, `currency CHAR(3)`, `status` (`pending`/`succeeded`/`failed`, enum in `app/db/constants`, CHECK constraint), `provider_transaction_id` (nullable), `failure_reason` (nullable). Indexes on `cart_id` and `user_id`, and a partial unique index for one active payment per cart. Model + `PaymentRepository` + schemas, following the CLAUDE.md rules (no SQL outside repositories, nested `with` statements).

## 6. Mock provider (decided)
- **Outcome by card token:** `tok_refused` → refused at start (402), `tok_unavailable` → provider error (502), `tok_declined` → accepted, then failed (debit: "insufficient funds", credit: "credit limit exceeded"), any other token → accepted, then succeeded.
- **Results are sent by `flask mock-provider settle`**, which calls the webhook through the API for every pending charge.
- **Payment types:** `user_payment_methods.type` (credit/debit), copied to `payments.payment_type`.

## 7. Pieces to build (after approval, in a new feature branch)
1. Payment status enum, model, migration, repository, schemas.
2. Total calculation service interface + stub (line items from `cart_items`).
3. Mock payment provider (after §6).
4. Payment service: validations → stock reservation → pending payment → provider call; webhook handling.
5. Endpoints (POST, GET, webhook) with Swagger docs.
6. Tests for every row of the tables in §3 and §4, plus duplicate requests and concurrency.
7. README: endpoint usage and all **[README]** decisions.

## Verification
- `alembic upgrade head` + `alembic check` with the payments migration.
- `pytest`: all §3/§4 cases, duplicate requests / double payment blocked.
- Manual check through Swagger at `/docs` with the `flask seed` data (Alice's active cart `c1c1…`, payment method `11111111-2222-3333-4444-555555555555`).
