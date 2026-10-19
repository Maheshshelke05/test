"""Mock payment gateway. The mock 'gateway' produces signed webhook events that go
through exactly the same idempotent handler a live provider's webhook would."""
import json
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..errors import ApiError
from ..models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentWebhookEvent,
    Refund,
    utcnow,
)
from ..realtime import emit, order_event
from ..security import constant_eq, hmac_hex
from .common import audit, notify


def sign(body: bytes) -> str:
    return hmac_hex(body, settings.webhook_secret)


def verify_signature(body: bytes, signature: str | None) -> bool:
    return bool(signature) and constant_eq(sign(body), signature)


def mock_gateway_event(order: Order, outcome: str) -> dict:
    return {
        "id": f"evt_{secrets.token_hex(10)}",
        "type": "payment.succeeded" if outcome == "success" else "payment.failed",
        "data": {"order_id": order.id, "amount_paise": order.total_paise,
                 "provider_ref": f"pay_{secrets.token_hex(8)}"},
    }


def process_event(db, event: dict) -> str:
    """Returns 'processed', 'duplicate' or 'ignored'. Exactly-once by event id."""
    try:
        db.add(PaymentWebhookEvent(event_id=event["id"], event_type=event["type"], payload=event))
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"

    data = event.get("data", {})
    order = db.get(Order, data.get("order_id"))
    if not order:
        db.commit()
        return "ignored"
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()))

    if event["type"] == "payment.succeeded":
        if data.get("amount_paise") != order.total_paise:
            audit(db, None, "payment.amount_mismatch", "order", order.id, event_id=event["id"])
            db.commit()
            return "ignored"
        if order.payment_status in (PaymentStatus.PAID, PaymentStatus.REFUND_PENDING, PaymentStatus.REFUNDED):
            db.commit()
            return "ignored"
        payment.status = PaymentStatus.PAID
        payment.provider_ref = data.get("provider_ref")
        order.payment_status = PaymentStatus.PAID
        order.paid_at = utcnow()
        if order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            # Money arrived after the order was closed (e.g. expired): refund it.
            db.add(Refund(payment_id=payment.id, order_id=order.id, amount_paise=payment.amount_paise,
                          reason="Payment received after order closed"))
            order.payment_status = PaymentStatus.REFUND_PENDING
        else:
            emit(db, f"kitchen:{order.kitchen_id}", "new_order", order_id=order.id,
                 order_number=order.order_number)
            notify(db, order.student_id, "Payment received",
                   f"Order {order.order_number} sent to {order.kitchen.name}.", order.id)
        order.version += 1
    elif event["type"] == "payment.failed":
        if order.payment_status != PaymentStatus.PENDING:
            db.commit()
            return "ignored"
        payment.status = PaymentStatus.FAILED
        order.payment_status = PaymentStatus.FAILED
        order.version += 1
        notify(db, order.student_id, "Payment failed",
               f"Payment for {order.order_number} failed. You can retry.", order.id)
    else:
        db.commit()
        return "ignored"

    audit(db, None, event["type"], "order", order.id, event_id=event["id"])
    order_event(db, order)
    db.commit()
    return "processed"


def retry_payment(db, order: Order):
    if order.payment_status != PaymentStatus.FAILED or order.status != OrderStatus.PENDING_ACCEPTANCE:
        raise ApiError(409, "CANNOT_RETRY", "This payment cannot be retried")
    order.payment_status = PaymentStatus.PENDING
    db.add(Payment(order_id=order.id, method=order.payment_method, amount_paise=order.total_paise))
    db.commit()


def event_bytes(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
