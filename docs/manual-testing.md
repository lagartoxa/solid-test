# Manual testing

How to try the payment API by hand, with Swagger and the sample data from `flask seed`: the happy path first, then every edge case.

## Before you start

1. Clear the database, create the tables and insert the sample data (see [How to run](../README.md#how-to-run)):
   ```bash
   ./dev.sh reset-db
   ```
2. Run the app (leave it running, and use another terminal for the other commands):
   ```bash
   ./dev.sh run
   ```
3. Open Swagger at http://localhost:5000/docs. For each call: open the endpoint, click **Try it out**, fill in the fields and click **Execute**.

> In Swagger, replace the example UUID (`3fa85f64-…`) in the request body with a real id from the tables below. The example UUID doesn't exist, so the API answers 409 `payment_method_not_found`.

### Sample data

Each user has a role in the tests:

| User | `User-Id` | Cart (`cart_id`) | Used for |
|---|---|---|---|
| Alice | `11111111-1111-1111-1111-111111111111` | `c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1` (1 kettle + 2 mugs = 70.00 USD) | the happy path |
| Bob | `22222222-2222-2222-2222-222222222222` | `c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2` | a user without payment methods |
| Carol | `33333333-3333-3333-3333-333333333333` | `c3c3c3c3-c3c3-c3c3-c3c3-c3c3c3c3c3c3` (1 mug = 12.50 USD) | the payment provider's failures |
| Dave | `44444444-4444-4444-4444-444444444444` | one cart per edge case (see [Edge cases](#edge-cases-start-a-payment)) | the validation edge cases |

Payment methods (`payment_method_id`):

| Owner | Id | Card | What the mock provider does |
|---|---|---|---|
| Alice | `11111111-2222-3333-4444-555555555555` | credit | accepts, then the charge succeeds |
| Carol | `33333333-2222-3333-4444-777777777777` | credit, `tok_refused` | refuses when the charge starts |
| Carol | `33333333-2222-3333-4444-888888888888` | credit, `tok_unavailable` | is unavailable when the charge starts |
| Carol | `33333333-2222-3333-4444-999999999999` | credit, `tok_declined` | accepts, then the charge fails ("credit limit exceeded") |
| Carol | `33333333-2222-3333-4444-aaaaaaaaaaaa` | debit, `tok_declined` | accepts, then the charge fails ("insufficient funds") |
| Dave | `44444444-2222-3333-4444-555555555555` | credit | accepts (Dave's carts fail before the charge) |

A successful payment checks the cart out, so the happy path can be run once per database reset (see [Start over](#start-over)). Carol's and Dave's tests don't change their carts, so they can be repeated as often as you want.

## How the result of a payment arrives

The payment is asynchronous. The POST only starts it; the payment provider reports the result later by calling our webhook (`POST /payments/webhook`). In these tests the provider is a mock, and this command plays it:

```bash
./dev.sh settle
```

It calls the webhook, signed and through the API, for **every** pending payment, and prints one line per payment (`<payment_id>: succeeded -> HTTP 200`).

> `settle` settles every pending payment in the database, not only the one you are testing. If a payment from another test is still pending, it gets its result too, and if it succeeds, its cart is checked out.

## Happy path (202): the payment starts and succeeds

1. **Start the payment.** `POST /carts/{cart_id}/payments`:
   - `cart_id`: `c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1`
   - `User-Id`: `11111111-1111-1111-1111-111111111111`
   - body: `{"payment_method_id": "11111111-2222-3333-4444-555555555555"}`

   Expected: **202 Accepted**, `"status": "pending"`. Copy the `id` from the response: it is the payment id.

2. **Read the status.** `GET /carts/{cart_id}/payments/{payment_id}`, with the same `cart_id` and `User-Id`, and the payment id from step 1.

   Expected: **200**, `"status": "pending"` (the provider hasn't answered yet).

   > Use the payment id (the `id` returned by step 1), not the payment method id. With the payment method id the API answers 404 `payment_not_found`.

3. **The provider sends the result:** run `./dev.sh settle`.

4. **Read the status again**, as in step 2.

   Expected: **200**, `"status": "succeeded"`. The cart is now `checked_out`: a new payment for it returns 409 `cart_not_active`.

## Payment provider failures (Carol)

All of these use Carol: `cart_id` `c3c3c3c3-c3c3-c3c3-c3c3-c3c3c3c3c3c3` and `User-Id` `33333333-3333-3333-3333-333333333333`. A failed payment gives the reserved stock back and leaves the cart `active`, so the tests can be repeated.

### 402: the provider refuses the charge

`POST /carts/{cart_id}/payments` with body `{"payment_method_id": "33333333-2222-3333-4444-777777777777"}`.

Expected: **402 Payment Required**:
```json
{"error": "payment_refused", "message": "The payment provider refused the charge: invalid card token."}
```
The payment is saved as `failed` with the reason "invalid card token".

### 502: the provider is unavailable

`POST /carts/{cart_id}/payments` with body `{"payment_method_id": "33333333-2222-3333-4444-888888888888"}`.

Expected: **502 Bad Gateway**, `"error": "provider_unavailable"`. The payment is saved as `failed` with the reason "payment provider is unavailable".

### 202, then failed: the charge is declined later

1. `POST /carts/{cart_id}/payments` with body `{"payment_method_id": "33333333-2222-3333-4444-999999999999"}` (or `…aaaaaaaaaaaa` for the debit card).

   Expected: **202**, `"status": "pending"`. Copy the payment `id`.

2. While it is pending, send the same POST again.

   Expected: **409** `active_payment_exists`. A cart can't have two pending or succeeded payments, so a double click can't charge twice.

3. Run `./dev.sh settle`, then `GET /carts/{cart_id}/payments/{payment_id}`.

   Expected: **200**, `"status": "failed"`, `"failure_reason": "credit limit exceeded"` (debit card: "insufficient funds"). The cart is still `active`.

## Edge cases: start a payment

`POST /carts/{cart_id}/payments`. Unless the table says otherwise, use Dave: `User-Id` `44444444-4444-4444-4444-444444444444` and body `{"payment_method_id": "44444444-2222-3333-4444-555555555555"}`. Every one of these leaves the data unchanged.

| Case | `cart_id` | What else to change | Expected |
|---|---|---|---|
| No `User-Id` | `e0000000-0000-0000-0000-000000000001` | leave `User-Id` empty | 422 |
| `User-Id` is not a UUID | `e0000000-0000-0000-0000-000000000001` | `User-Id`: `abc` | 422 |
| `cart_id` is not a UUID | `abc` | – | 422 |
| No `payment_method_id` | `e0000000-0000-0000-0000-000000000001` | body: `{}` | 422 |
| Unknown user | `e0000000-0000-0000-0000-000000000001` | `User-Id`: `99999999-9999-9999-9999-999999999999` | 404 `user_not_found` |
| Unknown cart | `99999999-9999-9999-9999-999999999999` | – | 404 `cart_not_found` |
| Deleted cart | `e0000000-0000-0000-0000-000000000004` | – | 404 `cart_not_found` |
| Another user's cart | `c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2` (Bob's) | – | 404 `cart_not_found` |
| Cart already checked out | `e0000000-0000-0000-0000-000000000002` | – | 409 `cart_not_active` |
| Cart abandoned | `e0000000-0000-0000-0000-000000000003` | – | 409 `cart_not_active` |
| User without payment methods | `c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2` | `User-Id`: `22222222-2222-2222-2222-222222222222` (Bob) | 409 `no_payment_method` |
| Payment method that doesn't exist | `e0000000-0000-0000-0000-000000000001` | body: `{"payment_method_id": "99999999-9999-9999-9999-999999999999"}` | 409 `payment_method_not_found` |
| Another user's payment method | `e0000000-0000-0000-0000-000000000001` | body: `{"payment_method_id": "11111111-2222-3333-4444-555555555555"}` (Alice's) | 409 `payment_method_not_found` |
| Empty cart | `e0000000-0000-0000-0000-000000000001` | – | 409 `cart_empty` |
| Cart with a deleted product | `e0000000-0000-0000-0000-000000000005` | – | 409 `product_unavailable` |
| Products in USD and EUR | `e0000000-0000-0000-0000-000000000006` | – | 409 `mixed_currencies` |
| Not enough stock (6 blankets, 5 in stock) | `e0000000-0000-0000-0000-000000000007` | – | 409 `insufficient_stock` |
| A payment is already pending | Carol's cart, see [202, then failed](#202-then-failed-the-charge-is-declined-later), step 2 | – | 409 `active_payment_exists` |

The 409 and 404 responses have the shape `{"error": "<code>", "message": "<text>"}`; the 422 responses list the invalid fields.

## Edge cases: read a payment

`GET /carts/{cart_id}/payments/{payment_id}`. First start a payment (for example Carol's [declined card](#202-then-failed-the-charge-is-declined-later)) to have a real payment id.

| Case | What to send | Expected |
|---|---|---|
| The payment | its cart, its payment id, its owner's `User-Id` | 200 with the payment |
| An id is not a UUID | `payment_id`: `abc` | 422 |
| Unknown cart | `cart_id`: `99999999-9999-9999-9999-999999999999` | 404 `cart_not_found` |
| Another user's cart | the right cart and payment, but another user's `User-Id` | 404 `cart_not_found` |
| Unknown payment | `payment_id`: `99999999-9999-9999-9999-999999999999` | 404 `payment_not_found` |
| Payment of another cart | Dave's cart `e0000000-0000-0000-0000-000000000001` and `User-Id` `44444444-4444-4444-4444-444444444444`, with Carol's payment id | 404 `payment_not_found` |
| Payment method id instead of payment id | `payment_id`: a `payment_method_id` | 404 `payment_not_found` |

## Edge cases: the webhook

Only the payment provider calls `POST /payments/webhook`, and every call must be signed with the shared secret (`X-Signature` header). Swagger can't compute the signature, so in Swagger you can only see the rejection:

| Case | What to send | Expected |
|---|---|---|
| No signature | any body, `X-Signature` empty | 401 `invalid_signature` |
| Wrong signature | any body, `X-Signature`: `abc` | 401 `invalid_signature` |

The signed cases use `./dev.sh settle` (see above) or curl. With the app running, replace the payment id and transaction id with those of a **pending** payment:

```bash
BODY='{"payment_id": "<payment id>", "provider_transaction_id": "<provider_transaction_id>", "status": "succeeded", "failure_reason": null}'
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "dev-webhook-secret" | awk '{print $2}')

curl -i -X POST http://localhost:5000/payments/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
```

| Case | Change | Expected |
|---|---|---|
| Succeeded | as above | 200, payment `succeeded`, cart `checked_out` |
| Failed | `"status": "failed", "failure_reason": "insufficient funds"` | 200, payment `failed`, stock given back, cart `active` |
| Failed without a reason | `"status": "failed", "failure_reason": null` | 422 |
| Unknown payment | a random `payment_id` | 404 `payment_not_found` |
| Repeated or late notification | send the same body again | 409 `payment_not_pending` |

The signature covers the exact body: recompute `SIGNATURE` every time `BODY` changes.

## Reading the logs

Every request, database change and call to the payment provider is saved in the logs. Two endpoints read them:

| Call | What it returns |
|---|---|
| `GET /logs/{log_id}` | one log entry |
| `GET /logs?request_id=<X-Request-ID>` | every log of one request: the API call, its database changes and its external calls |
| `GET /logs?record_id=<id>` | every change of one record, e.g. a payment id |
| `GET /logs?action=api_request&status_code=409` | every request that ended in 409 |
| `GET /logs?user_id=<User-Id>` | the requests of one user |

Filters can be combined; results are newest first, 50 per page (`limit` up to 200, `offset` for the next pages).

To try it in Swagger:

1. Run any test above, e.g. Dave's [empty cart](#edge-cases-start-a-payment) (409 `cart_empty`), and copy the `x-request-id` from the response headers.
2. `GET /logs` with `request_id` set to that id. Expected: **200** with the request's log: method and path, the headers and body received (card tokens masked as `***`), the response `{"error": "cart_empty", ...}`, the status code and the duration.
3. Start a payment that is accepted (e.g. with Carol's declined card: 202, it only fails later), copy its `id`, then `GET /logs` with `record_id` set to it. Expected: the payment's `insert` and `update`, with the values before and after.
4. `GET /logs/{log_id}` with the `id` of any entry from the steps above. Expected: **200** with that entry. With an unknown id: **404** `log_not_found`; with an id that isn't a UUID: **422**.

> Calls to the log endpoints are logged as well, but their successful responses are saved as a summary (`{"returned": ..., "total": ...}`), not as the logs they returned.

## Start over

The happy path checks out Alice's cart. To run it again, clear the database and insert the sample data again (this deletes all data, including the logs):

```bash
./dev.sh reset-db
```

## Where to look

Every request is saved in the `logs` table (readable with `GET /logs`, see [Reading the logs](#reading-the-logs)), with the same id as the `X-Request-ID` response header. That includes its database changes and its calls to the payment provider, and every edge case is logged with its error code. Every payment and cart status change is kept in `payments_history` and `carts_history`.
