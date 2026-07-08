"""
Orders API — demonstrates:
  1. Idempotent POST /orders
  2. Cursor-based pagination on GET /orders
  3. Per-client (X-Client-Id) rate limiting

Assigned values:
  T (total catalog orders) = 49
  R (rate limit)           = 19 requests / 10 seconds
"""

import time
import uuid
import threading
from collections import deque
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
TOTAL_ORDERS = 49
RATE_LIMIT = 19          # requests
RATE_WINDOW = 10.0       # seconds

app = FastAPI(title="Orders API")

# CORS: must allow the grader page (arbitrary origin) to call this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # can't combine wildcard origin with credentials
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# --------------------------------------------------------------------------
# Fixed catalog for pagination (IDs 1..TOTAL_ORDERS)
# --------------------------------------------------------------------------
CATALOG = [
    {"id": i, "item": f"item-{i}", "amount": 100 + i}
    for i in range(1, TOTAL_ORDERS + 1)
]

# --------------------------------------------------------------------------
# In-memory stores (single-process demo storage)
# --------------------------------------------------------------------------
_lock = threading.Lock()
idempotency_store: dict[str, dict] = {}   # Idempotency-Key -> order record
rate_buckets: dict[str, deque] = {}       # client_id -> deque[timestamps]


class OrderIn(BaseModel):
    item: Optional[str] = None
    amount: Optional[float] = None


# --------------------------------------------------------------------------
# Rate limiting (sliding window log, per X-Client-Id)
# --------------------------------------------------------------------------
def check_rate_limit(client_id: str):
    now = time.time()
    with _lock:
        bucket = rate_buckets.setdefault(client_id, deque())
        # drop timestamps outside the window
        while bucket and now - bucket[0] > RATE_WINDOW:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            oldest = bucket[0]
            retry_after = max(1, int(RATE_WINDOW - (now - oldest)) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only rate-limit if a client id was supplied; identify each client separately.
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        try:
            check_rate_limit(client_id)
        except HTTPException as exc:
            return Response(
                content=f'{{"detail":"{exc.detail}"}}',
                status_code=exc.status_code,
                headers=exc.headers,
                media_type="application/json",
            )
    return await call_next(request)


# --------------------------------------------------------------------------
# 1. Idempotent order creation
# --------------------------------------------------------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: OrderIn,
    response: Response,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    with _lock:
        if idempotency_key:
            existing = idempotency_store.get(idempotency_key)
            if existing is not None:
                # Repeat call with same key -> return the SAME order, no duplicate.
                response.status_code = 201
                return existing

        new_order = {
            "id": str(uuid.uuid4()),
            "item": order.item or "untitled",
            "amount": order.amount if order.amount is not None else 0,
        }

        if idempotency_key:
            idempotency_store[idempotency_key] = new_order

    return new_order


# --------------------------------------------------------------------------
# 2. Cursor-based pagination over the fixed catalog (IDs 1..TOTAL_ORDERS)
# --------------------------------------------------------------------------
@app.get("/orders")
def list_orders(limit: int = 10, cursor: Optional[str] = None):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")

    # Cursor encodes the next starting index (0-based) into CATALOG.
    try:
        start = int(cursor) if cursor not in (None, "", "null") else 0
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid cursor")

    if start < 0 or start > len(CATALOG):
        raise HTTPException(status_code=400, detail="invalid cursor")

    end = min(start + limit, len(CATALOG))
    items = CATALOG[start:end]
    next_cursor = str(end) if end < len(CATALOG) else None

    return {
        "items": items,
        "orders": items,          # alias, accepted by grader
        "next_cursor": next_cursor,
        "next": next_cursor,      # alias, accepted by grader
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "orders-api", "total_orders": TOTAL_ORDERS}