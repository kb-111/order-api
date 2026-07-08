from fastapi import FastAPI, Header, Response, Request
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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# -----------------------------
# Constants
# -----------------------------
TOTAL_ORDERS = 49
RATE_LIMIT = 19
WINDOW = 10  # seconds

# -----------------------------
# In-memory storage
# -----------------------------
orders_created = {}   # Idempotency-Key -> Order
rate_limits = {}      # Client ID -> timestamps

# -----------------------------
# Models
# -----------------------------
class OrderRequest(BaseModel):
    item: str = "Sample Item"


# -----------------------------
# Rate Limiting Middleware
# -----------------------------
@app.middleware("http")
async def rate_limiter(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id")

    if client_id:

        now = time.time()

        timestamps = rate_limits.get(client_id, [])

        # Keep only timestamps in last 10 seconds
        timestamps = [t for t in timestamps if now - t < WINDOW]

        if len(timestamps) >= RATE_LIMIT:

            retry_after = max(1, int(WINDOW - (now - timestamps[0])) + 1)

            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": str(retry_after)
                },
            )

        timestamps.append(now)
        rate_limits[client_id] = timestamps

    response = await call_next(request)
    return response


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders")
def create_order(
    order: OrderRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):

    if idempotency_key in orders_created:
        response.status_code = 201
        return orders_created[idempotency_key]

    new_order = {
        "id": str(uuid.uuid4()),
        "item": order.item
    }

    orders_created[idempotency_key] = new_order

    response.status_code = 201

    return new_order


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def get_orders(limit: int = 10, cursor: str | None = None):

    if limit <= 0:
        limit = 10

    if cursor is None:
        start = 1
    else:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            start = 1

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = []

    for i in range(start, end + 1):
        items.append({
            "id": i,
            "name": f"Order {i}"
        })

    if end >= TOTAL_ORDERS:
        next_cursor = None
    else:
        next_cursor = base64.b64encode(
            str(end + 1).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------------
# Root endpoint (optional)
# -----------------------------
@app.get("/")
def root():
    return {
        "message": "Orders API is running."
    }
