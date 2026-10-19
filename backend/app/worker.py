"""Background jobs: expire unpaid orders, settle refunds, flag slow acceptance.

Runs inside the API process by default (RUN_WORKER=true). For multiple API
instances, set RUN_WORKER=false on them and run `python -m app.worker` once."""
import asyncio
import logging
import time
from datetime import timedelta

from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .models import Order, OrderStatus, Payment, PaymentMethod, PaymentStatus, Refund, utcnow
from .realtime import emit
from .services import ordering
from .services.common import audit, notify

log = logging.getLogger("campusbite.worker")


def expire_unpaid_orders(db) -> int:
    cutoff = utcnow() - timedelta(minutes=settings.unpaid_order_expiry_minutes)
    stale = db.scalars(select(Order).where(
        Order.status == OrderStatus.PENDING_ACCEPTANCE,
        Order.payment_method.in_(PaymentMethod.ONLINE),
        Order.payment_status.in_((PaymentStatus.PENDING, PaymentStatus.FAILED)),
        Order.created_at < cutoff)).all()
    for o in stale:
        try:
            ordering.transition(db, o, OrderStatus.CANCELLED, None, None, note="Payment not completed in time")
        except Exception as exc:  # another actor moved it; skip
            db.rollback()
            log.info("skip expire %s: %s", o.id, exc)
    return len(stale)


def settle_refunds(db) -> int:
    """Mock refund processor. A live gateway would confirm via webhook instead."""
    pending = db.scalars(select(Refund).where(Refund.status == "INITIATED")).all()
    for r in pending:
        r.status = "SUCCEEDED"
        payment = db.get(Payment, r.payment_id)
        payment.status = PaymentStatus.REFUNDED
        order = db.get(Order, r.order_id)
        order.payment_status = PaymentStatus.REFUNDED
        order.version += 1
        notify(db, order.student_id, "Refund processed",
               f"₹{r.amount_paise / 100:.2f} for {order.order_number} has been refunded.", order.id)
        audit(db, None, "refund.succeeded", "order", order.id, refund_id=r.id)
        db.commit()
    return len(pending)


def flag_slow_acceptance(db) -> int:
    cutoff = utcnow() - timedelta(minutes=settings.accept_timeout_minutes)
    rows = db.scalars(select(Order).where(
        Order.status == OrderStatus.PENDING_ACCEPTANCE, Order.ack_overdue_flagged.is_(False),
        # Online orders reach the kitchen when paid, so the clock starts then.
        func.coalesce(Order.paid_at, Order.created_at) < cutoff)).all()
    n = 0
    for o in rows:
        if not ordering.is_payable_for_kitchen(o):
            continue
        o.ack_overdue_flagged = True
        emit(db, f"kitchen:{o.kitchen_id}", "ack_overdue", order_id=o.id, order_number=o.order_number)
        emit(db, "admin", "ack_overdue", order_id=o.id, order_number=o.order_number)
        audit(db, None, "order.ack_overdue", "order", o.id)
        n += 1
    db.commit()
    return n


def run_once() -> dict:
    with SessionLocal() as db:
        return {"expired": expire_unpaid_orders(db), "refunds": settle_refunds(db),
                "ack_overdue": flag_slow_acceptance(db)}


async def loop_forever():
    while True:
        try:
            result = await asyncio.to_thread(run_once)
            if any(result.values()):
                log.info("worker: %s", result)
        except Exception:
            log.exception("worker iteration failed")
        await asyncio.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .realtime import hub

    settings.check_production()
    # Without this, events from this process (refunds, expiries, late-acceptance alerts)
    # would never reach the API processes' WebSocket clients.
    log.info("worker started; realtime via %s", "Redis" if hub.connect_publisher() else "nothing (no REDIS_URL)")
    while True:
        try:
            result = run_once()
            if any(result.values()):
                log.info("worker: %s", result)
        except Exception:
            log.exception("worker iteration failed")
        time.sleep(settings.worker_interval_seconds)
