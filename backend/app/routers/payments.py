import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..errors import ApiError
from ..services import payments

router = APIRouter(prefix="/v1/payments", tags=["payments"])


@router.post("/webhook")
async def webhook(request: Request, x_signature: str | None = Header(default=None),
                  db: DbSession = Depends(get_db)):
    """Gateway webhook: verify HMAC signature, then process idempotently by event id."""
    body = await request.body()
    if not payments.verify_signature(body, x_signature):
        raise ApiError(401, "BAD_SIGNATURE", "Invalid webhook signature")
    try:
        event = json.loads(body)
    except ValueError:
        raise ApiError(400, "BAD_PAYLOAD", "Invalid JSON")
    return {"result": payments.process_event(db, event)}
