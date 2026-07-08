"""
IITM BS TDS Week 2 GA2
Orders API

Features:
1. Idempotent POST /orders
2. Cursor pagination GET /orders
3. Per-client rate limiting

Assigned:
T = 49 orders
R = 19 requests / 10 seconds
"""

import time
import uuid
import threading
from collections import defaultdict, deque
from typing import Optional, Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
    expose_headers=["Retry-After"],
)


# --------------------------------------------------
# Configuration
# --------------------------------------------------

TOTAL_ORDERS = 49
RATE_LIMIT = 19
WINDOW = 10


# --------------------------------------------------
# Fixed order catalog
# IDs must be 1 to 49
# --------------------------------------------------

ORDERS = [
    {
        "id": i,
        "item": f"item-{i}",
        "amount": 100 + i
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


# --------------------------------------------------
# Storage
# --------------------------------------------------

idempotency_store = {}

rate_store = defaultdict(deque)

lock = threading.Lock()



# --------------------------------------------------
# Rate limiter
# --------------------------------------------------

def check_rate(client_id: str):

    now = time.time()

    with lock:

        bucket = rate_store[client_id]

        while bucket and now - bucket[0] >= WINDOW:
            bucket.popleft()


        if len(bucket) >= RATE_LIMIT:

            retry = int(WINDOW - (now - bucket[0])) + 1

            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(retry)
                }
            )


        bucket.append(now)



@app.middleware("http")
async def rate_limit_middleware(
    request: Request,
    call_next
):

    client_id = request.headers.get("X-Client-Id")

    if client_id:
        try:
            check_rate(client_id)

        except HTTPException as e:

            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                headers={
                    "Retry-After": e.headers["Retry-After"]
                },
                media_type="application/json"
            )


    return await call_next(request)



# --------------------------------------------------
# 1. Idempotent order creation
# --------------------------------------------------

@app.post("/orders", status_code=201)
async def create_order(
    body: dict[str, Any],
    response: Response,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key"
    )
):

    with lock:

        # Existing key
        if idempotency_key in idempotency_store:

            response.status_code = 201

            return idempotency_store[idempotency_key]


        order = {
            "id": str(uuid.uuid4()),
            **body
        }


        idempotency_store[idempotency_key] = order


    response.status_code = 201

    return order



# --------------------------------------------------
# 2. Cursor pagination
# --------------------------------------------------

@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    if limit < 1:
        limit = 10


    # cursor represents next index
    if cursor is None:

        start = 0

    else:

        try:
            start = int(cursor)

        except:

            start = 0



    end = min(
        start + limit,
        TOTAL_ORDERS
    )


    items = ORDERS[start:end]


    if end < TOTAL_ORDERS:

        next_cursor = str(end)

    else:

        next_cursor = None



    return {
        "items": items,
        "next_cursor": next_cursor
    }



# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/")
def root():

    return {
        "status": "ok"
    }
