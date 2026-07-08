from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# In-memory storage
# -----------------------------
orders_created = {}
rate_limits = {}

TOTAL_ORDERS = 49
RATE_LIMIT = 19
WINDOW = 10  # seconds


# -----------------------------
# Models
# -----------------------------
class OrderRequest(BaseModel):
    item: str = "Sample Item"


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: OrderRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    if idempotency_key in orders_created:
        return orders_created[idempotency_key]

    new_order = {
        "id": str(uuid.uuid4()),
        "item": order.item
    }

    orders_created[idempotency_key] = new_order

    return new_order


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(limit: int = 10, cursor: str | None = None):

    if cursor is None:
        start = 1
    else:
        start = int(base64.b64decode(cursor).decode())

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [
        {
            "id": i,
            "name": f"Order {i}"
        }
        for i in range(start, end + 1)
    ]

    if end >= TOTAL_ORDERS:
        next_cursor = None
    else:
        next_cursor = base64.b64encode(str(end + 1).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------------
# Rate Limiting Middleware
# -----------------------------
@app.middleware("http")
async def limiter(request, call_next):

    client = request.headers.get("X-Client-Id")

    if client:

        now = time.time()

        timestamps = rate_limits.get(client, [])

        timestamps = [
            t for t in timestamps
            if now - t < WINDOW
        ]

        if len(timestamps) >= RATE_LIMIT:

            retry = WINDOW - (now - timestamps[0])

            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": str(int(retry) + 1)
                },
            )

        timestamps.append(now)

        rate_limits[client] = timestamps

    response = await call_next(request)

    return response