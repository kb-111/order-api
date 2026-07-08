from fastapi import FastAPI, Header, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
import uuid
import time
import base64


app = FastAPI()


# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


# -----------------------------
# Assignment values
# -----------------------------
TOTAL_ORDERS = 49
RATE_LIMIT = 19
WINDOW = 10


# -----------------------------
# Storage
# -----------------------------
idempotency_store = {}
rate_limit_store = {}


# -----------------------------
# Rate limiter middleware
# -----------------------------
@app.middleware("http")
async def rate_limiter(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id")

    if client_id:

        now = time.time()

        requests = rate_limit_store.get(client_id, [])

        # remove expired requests
        requests = [
            t for t in requests
            if now - t < WINDOW
        ]

        if len(requests) >= RATE_LIMIT:

            retry_after = int(
                WINDOW - (now - requests[0])
            ) + 1

            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": str(retry_after)
                }
            )

        requests.append(now)
        rate_limit_store[client_id] = requests


    response = await call_next(request)

    return response



# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders")
async def create_order(
    order: dict[str, Any],
    response: Response,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key"
    )
):

    # Existing key -> return same order
    if idempotency_key in idempotency_store:

        response.status_code = 201

        return idempotency_store[idempotency_key]


    # Create new order
    new_order = {
        "id": str(uuid.uuid4()),
        **order
    }


    idempotency_store[idempotency_key] = new_order

    response.status_code = 201

    return new_order



# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: str | None = None
):

    if limit <= 0:
        limit = 10


    limit = min(limit, TOTAL_ORDERS)


    # Decode cursor
    if cursor:

        try:
            start = int(
                base64.b64decode(cursor).decode()
            )

        except Exception:
            start = 1

    else:
        start = 1



    end = min(
        start + limit - 1,
        TOTAL_ORDERS
    )


    items = []

    for i in range(start, end + 1):

        items.append(
            {
                "id": i,
                "name": f"Order {i}"
            }
        )


    # next cursor
    if end < TOTAL_ORDERS:

        next_cursor = base64.b64encode(
            str(end + 1).encode()
        ).decode()

    else:

        next_cursor = None



    return {
        "items": items,
        "next_cursor": next_cursor
    }



# -----------------------------
# Health check
# -----------------------------
@app.get("/")
def home():

    return {
        "message": "Orders API running"
    }