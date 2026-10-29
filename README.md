# Payment Endpoint

Payment part of an online shop: a SQL schema for payments and an HTTP endpoint that starts the payment for a cart. The task is described in [instructions.md](instructions.md).

## Stack

- Python 3.10+, Flask, SQLAlchemy 2
- PostgreSQL 16 (Docker)
- Alembic for migrations
- Pydantic for API request/response schemas and repository input
- flask-openapi3 for the OpenAPI spec and the Swagger UI
- pytest

## Project structure

```
app/
├── __init__.py          # create_app() factory
├── config.py            # settings from environment variables (.env)
├── cli.py               # `flask seed` and `flask mock-provider settle` commands
├── log/                 # action logger (singleton) and API request logging
├── db/
│   ├── session.py       # engine and one session per request
│   ├── constants/       # enums used by the models (e.g. CartStatus)
│   ├── models/          # SQLAlchemy models; base.py has BaseModel
│   └── repositories/    # CRUD layer; base.py has BaseRepository
├── schemas/             # Pydantic schemas: API input/responses and repository input
├── api/                 # HTTP endpoints and error responses
└── services/            # payment service, payment provider (mock), total calculation (stub)
alembic/                 # migrations
tests/
├── conftest.py          # database and app fixtures
├── factories.py         # test data factories, request helpers and assertions
├── unit/
└── integration/
    └── api/             # one test file per endpoint (+ the mock settlement end to end)
docker/postgres/         # database init script (creates the test database)
docker-compose.yml       # PostgreSQL and the app
Dockerfile               # image of the app (also runs the tests)
dev.sh                   # reset-db, run, test, settle and down commands
requirements/
├── base.txt             # runtime dependencies
└── dev.txt              # base + test dependencies
```

## How to run

Requirements: Docker with Docker Compose (`docker compose` or `docker-compose`) and bash. Everything runs in containers: the API, PostgreSQL and the tests.

```bash
# 1. Clear the database, create the tables and insert the sample data
./dev.sh reset-db

# 2. Run the API at http://localhost:5000 (Swagger at http://localhost:5000/docs); Ctrl+C stops it
./dev.sh run

# 3. Run the automated tests
./dev.sh test
```

Other commands:

| Command | What it does |
|---|---|
| `./dev.sh settle` | The mock payment provider sends the result of every pending payment (see [Using the payment API](#using-the-payment-api)) |
| `./dev.sh down` | Stops the containers; the data is kept |

Ports 5000 (API) and 5432 (PostgreSQL) must be free. `./dev.sh reset-db` deletes all the data, so run it again whenever you want to start the tests from scratch.

### Without Docker for the app

To run the app and the tests directly with Python 3.10+ (PostgreSQL still runs in Docker):

```bash
docker-compose up -d db
python3 -m venv .venv
.venv/bin/pip install -r requirements/dev.txt
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/flask seed
.venv/bin/flask run          # the API
.venv/bin/pytest             # the tests
```

`flask seed` can run more than once. It inserts only the sample records that are not in the database yet.

## API documentation

With the app running, open http://localhost:5000/docs for the Swagger UI. The OpenAPI spec is at http://localhost:5000/docs/openapi.json.

## Using the payment API

| Endpoint | What it does |
|---|---|
| `POST /carts/{cart_id}/payments` | Starts the payment of a cart. Header `User-Id`, body `{"payment_method_id": ...}`. Returns 202 with the `pending` payment. |
| `GET /carts/{cart_id}/payments/{payment_id}` | Reads the payment and its status (`pending`, `succeeded` or `failed`). Header `User-Id`. |
| `POST /payments/webhook` | Called by the payment provider with the result of a charge. Signed with the `X-Signature` header. |

Business errors return `{"error": "<code>", "message": "<text>"}` (e.g. `cart_not_active`, `insufficient_stock`); invalid input returns 422. The flows are drawn in [docs/diagrams/](docs/diagrams/) (PlantUML), and every error, with how to trigger it, is in [docs/manual-testing.md](docs/manual-testing.md).

**Trying it.** After `flask seed`, Alice (`User-Id: 11111111-1111-1111-1111-111111111111`) has an active cart (`c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1`) and one card per outcome of the mock provider:

| Payment method id | Card | Result |
|---|---|---|
| `11111111-2222-3333-4444-555555555555` | credit | 202, then succeeded |
| `11111111-2222-3333-4444-666666666666` | debit | 202, then succeeded |
| `11111111-2222-3333-4444-777777777777` | credit, `tok_refused` | 402, payment failed ("invalid card token") |
| `11111111-2222-3333-4444-888888888888` | credit, `tok_unavailable` | 502, payment failed (provider unavailable) |
| `11111111-2222-3333-4444-999999999999` | credit, `tok_declined` | 202, then failed ("credit limit exceeded") |
| `11111111-2222-3333-4444-aaaaaaaaaaaa` | debit, `tok_declined` | 202, then failed ("insufficient funds") |

Bob (`22222222-2222-2222-2222-222222222222`) has an active cart (`c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2`) but no payment method (409 `no_payment_method`). Carol (`33333333-3333-3333-3333-333333333333`) has an active cart and one card per failure of the provider, so failures can be tested without using up Alice's cart. Dave (`44444444-4444-4444-4444-444444444444`) has a working card and one cart per edge case (empty, checked out, abandoned, deleted, with a deleted product, mixed currencies, not enough stock). Step-by-step instructions: [docs/manual-testing.md](docs/manual-testing.md).

The provider's result arrives later. To send it, run the mock provider's settle command; it calls the webhook (signed, through the API) for every pending charge:

```bash
./dev.sh settle
```

## How to test

```bash
./dev.sh test
```

Without Docker for the app (see above): `.venv/bin/pytest`, or `.venv/bin/pytest --cov=app` for coverage.

To test the API by hand with Swagger, step by step for the happy path and every edge case, see [docs/manual-testing.md](docs/manual-testing.md).

The tests use the `shop_test` database. They apply the Alembic migrations at the start, so the tests always check the real schema, and remove the tables at the end. Each test runs inside a transaction that is rolled back, so tests do not share data.

## Decisions so far

- **Base schema.** The tables from [quick-start.sql](quick-start.sql) are recreated as SQLAlchemy models and as the first Alembic migration. The file stays in the repository as a reference. Column types, defaults, checks and index names are the same.
- **BaseModel.** All tables inherit from `BaseModel` ([app/db/models/base.py](app/db/models/base.py)). It gives every table:
  - `id`: UUID primary key, generated by the database (`gen_random_uuid()`).
  - `created_at` and `updated_at`: the base schema already had them on most tables, so I kept those names. `cart_items` and `user_payment_methods` had no `updated_at`; they get it now. `updated_at` is set with `clock_timestamp()` on every ORM update, because `now()` returns the start time of the transaction.
  - `deleted_at`: soft delete. A row is deleted when `deleted_at` is not `NULL`. Nothing is removed from the database.
- **Soft delete details.**
  - `users.email` is unique only among rows that are not deleted (partial unique index), so a deleted user's email can be used again.
  - A soft delete does not cascade. When a cart is soft deleted, its items stay as they are. `ON DELETE CASCADE` on `cart_items` still works for a real delete.
- **Repositories for CRUD.** All database access goes through repositories ([app/db/repositories/](app/db/repositories/)), based on the structure I used in my project [fii](https://github.com/lagartoxa/fii/tree/master/backend/app/db/repositories). `BaseRepository` has `create`, `update`, `delete` (soft), `restore`, `get_by_id` and `get_all`. Queries skip soft-deleted rows unless `include_deleted=True`.
  - The goal of the repositories is that every database connection is closed properly. A repository is always used in a `with` statement. When the block ends, it commits (or rolls back on error) and closes the session, which returns the connection to the pool.
  - To use more than one repository in the same transaction, the `with` statements are nested and share the same session. Only the outermost `with` commits or rolls back and closes the session. An error at any level rolls back everything.
  - The session is created with `expire_on_commit=False`, so the objects returned by a repository keep their values after the session is closed. Relationships that were not loaded inside the `with` block cannot be loaded after it.
  - The only code that uses the session directly is the `flask seed` command, because it only populates the database with sample data.
- **Migrations.** Alembic manages the schema. The payments table was added as a new migration, as `quick-start.sql` asks. The sample data is not in a migration; `flask seed` inserts it, so a production database never gets test data.
- **Versioned tables.** Any table can keep the full history of its changes by inheriting from `VersionedBaseModel` instead of `BaseModel` ([app/db/models/base.py](app/db/models/base.py)) and generating a migration. Each insert, update, soft delete or hard delete writes a snapshot of the row to `<table>_history`, with the version, the operation and when it happened, in the same transaction as the change. `carts` is versioned, so every cart status change is kept. **This was decided so the history can be used to debug errors later**, for example to see which states a cart went through around a failed payment. It records what changed and when, not who (see the traceability note in the assumptions).
  - The `version` column is also used for optimistic locking: updating a row that another request changed in the meantime raises an error instead of silently overwriting that change.
  - History is written by SQLAlchemy session events, so only changes made through ORM objects (as the repositories do) are recorded. Bulk `UPDATE` statements skip it and must not be used on versioned tables.
  - History is read with `get_history(id)` on the repository (`VersionedBaseRepository`).
- **Action log.** Every action done by the API is saved in the `logs` table. **The goal is to track errors later.**
  - What is logged:
    - every API request with its headers, query string and body, plus the response status and body, the error traceback (if any) and the duration;
    - every database change, with the values before and after;
    - every call to an external service (payment provider, total calculation service), with the payloads sent and received.
  - Every request gets an id. It is saved on all the logs of that request and returned in the `X-Request-ID` response header.
  - Unexpected errors return 500 with `{"error": "An unexpected error happened. Log id: <request_id>/<log_id>", "request_id": ..., "log_id": ...}`. The request id finds every log of the request (its database changes and external calls); the log id finds the exact log row with the traceback. **Both ids are given to make debugging easier**: the support team can trace the error from what the user reports.
  - The caller's user id comes in the `User-Id` header and is saved on every log of the request. The header has no underscore because some servers (nginx, gunicorn) drop headers with underscores.
  - API requests and external calls are saved in their own transaction, so they are kept even when the request fails and rolls back, which is when they are needed. Database changes are logged in the same transaction as the change, so a rolled-back change leaves no log of a change that never happened.
  - Sensitive values (card tokens, passwords, authorization headers, ...) are replaced with `***` before saving.
  - The logger is a singleton (`ActionLogger` in [app/log/action_logger.py](app/log/action_logger.py)), so the whole app writes logs the same way.
  - Database changes are logged by explicit calls in the repositories (`BaseRepository` does it for create, update, delete and restore), not by an automatic listener.
  - The Swagger pages (`/docs`) are not logged; they are not API actions.
  - If a log can't be saved, the request still works and the failure goes to the Python logger.
  - The `logs` table is append-only, so it doesn't inherit `BaseModel` (no `updated_at` or soft delete), like the `*_history` tables.
  - I may have been a little overkill with the logging, but I come from an automation background where, unfortunately, nobody logs anything. Since I was the one expected to troubleshoot and fix just about everything, especially early on, I learned to log absolutely everything. It was a matter of survival.
- **No `Idempotency-Key`.** The task doesn't ask for it, and duplicate payment requests (double click, network retry) are already blocked: a cart can have only one pending or succeeded payment, so a duplicate request gets 409 and the client can read the payment's status. No double charge is possible (KISS). A real system whose clients retry automatically would add an `Idempotency-Key`, so a retry gets the original response instead of 409.
- **Provider errors when starting a charge.** If the provider refuses the charge (e.g. invalid card token), the API returns 402. If it is unreachable, times out or answers with an error, it returns 502, not 409: the request and the data were fine, a service we depend on failed. In both cases the payment is saved as failed with the reason, the reserved stock is given back and the cart stays active, so the user can retry.
- **Payment webhook security.** The provider's notifications (`POST /payments/webhook`) must be signed with a shared secret (an HMAC of the body, secret from the configuration). Without it, anyone could call the webhook and mark a payment as paid. A missing or wrong signature returns 401.
- **Late or repeated webhooks.** A notification for a payment that is no longer `pending` returns 409. This should be evaluated in real life: if providers resend notifications often, I would answer 200 for a repeated notification with the same status instead.
- **Payment endpoint.**
  - The caller is identified by the `User-Id` header, and the cart must belong to that user. In a real system this would be an authentication token; here that felt like overkill.
  - The payment method is a required field. The API never picks one by itself (not even the default), because that decision is too critical: the UI decides which method is sent. A user without payment methods, or a method that is missing, deleted or another user's, returns 409.
  - A cart with products in different currencies returns 409: one card charge has one currency. I took this decision because I don't see this happening in real life, but I would discuss it with the customer first.
  - The payment is asynchronous: the POST reserves the stock, saves the payment as `pending`, starts the charge and returns 202. The result arrives later through the webhook. Succeeded: the cart becomes `checked_out`. Failed: the reserved stock is given back and the cart stays `active`, so the user can retry.
  - The checks and the stock reservation run in one transaction, with the cart and the products locked (`SELECT ... FOR UPDATE`), and are committed before the provider is called, so the provider call never holds the locks. A partial unique index also allows only one pending or succeeded payment per cart. A concurrent change of the same cart (`StaleDataError`) or payment returns 409.
  - All business errors have the same response shape, `{"error": "<code>", "message": "<text>"}`, with a stable code per edge case. Every edge case is logged with its code (the API log saves the response).
  - `payments` is versioned like `carts`, so every payment status change is kept in `payments_history`.
  - Assumption: cart items don't change while a payment is pending (cart management is outside this task); the stock given back on a failure is based on the cart items.
- **Payment types.** A payment method is a `credit` or `debit` card (`user_payment_methods.type`, existing methods became `credit`). The payment copies the type, so it keeps the type it was charged with. The flow is the same for both; only the mock's decline reason differs.
- **External services.** The payment provider and the payment total calculation service are interfaces (`PaymentProvider`, `TotalCalculationService`) injected into the payment service, so the real ones can replace the mock and the stub without changing it.
  - The total calculation stub returns the cart items as line items (quantity and unit price); the payment service sums them.
  - The mock provider decides by card token, like the test cards of real providers' sandboxes: `tok_refused` refuses when the charge starts (402), `tok_unavailable` fails (502), `tok_declined` is accepted and later fails (debit: "insufficient funds", credit: "credit limit exceeded"), any other token is accepted and later succeeds.
  - The mock sends its results with the `flask mock-provider settle` command, which calls the webhook through the API (validated, signed and logged like a real call). Simple and easy to run during a demo; a background thread would be closer to reality but harder to test and explain.
- **Idempotent seed.** Every sample record has a fixed id (the ids from `quick-start.sql`, plus fixed ids for the cart items, which had none). Before inserting a record, the seed checks if its id already exists, including soft-deleted rows, and skips it. Running the seed again never creates duplicates or fails.
- **Enums in `db/constants`.** Enums such as `CartStatus` are in [app/db/constants/](app/db/constants/), not in the model files. Models, schemas and services import them from one place. CHECK constraints are built from the enums (`enum_check`), so the allowed values are written only once.
- **API docs with Swagger.** The app is built with `flask-openapi3`, a Flask subclass that creates the OpenAPI spec from the routes and their Pydantic schemas, so the docs always match the code. Swagger UI is served at `/docs`.
- **Docker for the evaluation.** The API, PostgreSQL and the tests run in containers, so trying the project only needs Docker. `dev.sh` wraps the Docker Compose commands (`reset-db`, `run`, `test`, `settle`, `down`) and works with both Compose v1 and v2. Nothing is automatic on start: the database is cleared and filled only by `./dev.sh reset-db`, so a restart never changes the data during a test. The app runs on Flask's development server, which is enough for an evaluation; production would use a WSGI server (e.g. gunicorn).
- **Requirements split.** `requirements/base.txt` has what the app needs to run. `requirements/dev.txt` adds the test tools.
- **Tests.** The tests use a real PostgreSQL database instead of SQLite, because the schema uses PostgreSQL features (UUID generation, partial indexes).
- **Commit messages as versioning documents.** Every commit message is written so it can be reused later in a versioning document (changelog / release notes): a short imperative subject line saying what changed, and a body with what changed and why, the schema or user-visible impact, and any new migration, config or dependency. The tests must all pass before a commit is made.
- **Instructions file for the AI agent.** Since I used Claude for this task, I wrote the project rules in [CLAUDE.md](CLAUDE.md), a file that Claude Code loads automatically in every session, so all new code follows the same rules: commit only when asked, run the tests and get my approval of the commit message before committing, no SQL outside repositories (nested `with` statements when more than one repository is needed), how to use versioned tables, ask instead of assuming on ambiguous instructions, and follow DRY and KISS.

## My Assumptions

Since no instructions told otherwise, I assumed I could use AI for the task, so I used Claude. I really don't remember if we agreed on something different at the meeting. If so, I apologise and I can do the task again without AI.

Said that, I can explain any code on this project. Understanding the code I'm shipping will always be a requirement for me.

On a real system I would also implement RBAC for authentication and permissions. Here I thought it would be overkill (KISS principle).

About the traceability, it would be better to save every change with the user that made it and not only the last change but again, overkill.
