"""Quote, order creation, the fulfillment state machine and pickup verification."""
import secrets
from collections import Counter
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..errors import ApiError, not_found
from ..models import (
    Kitchen,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus as S,
    OrderStatusHistory,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Refund,
    User,
    utcnow,
)
from ..realtime import emit, order_event
from ..security import constant_eq, hmac_hex, sha256
from .common import audit, flag_enabled, kitchen_orderable, notify

# Allowed fulfillment transitions. Payment state is tracked separately.
TRANSITIONS = {
    S.PENDING_ACCEPTANCE: {S.ACCEPTED, S.REJECTED, S.CANCELLED},
    S.ACCEPTED: {S.PREPARING, S.CANCELLED},
    S.PREPARING: {S.READY, S.CANCELLED},
    S.READY: {S.COMPLETED, S.CANCELLED},
}

STUDENT_MESSAGES = {
    S.ACCEPTED: ("Order accepted", "{kitchen} accepted order {num}. Ready in about {eta} min."),
    S.PREPARING: ("Being prepared", "{kitchen} is preparing order {num}."),
    S.READY: ("Ready for pickup!", "Order {num} is ready at {counter}. Show your pickup code."),
    S.COMPLETED: ("Enjoy your meal", "Order {num} was collected. Thanks for ordering!"),
    S.REJECTED: ("Order rejected", "{kitchen} could not take order {num}: {reason}"),
    S.CANCELLED: ("Order cancelled", "Order {num} was cancelled: {reason}"),
}


# ---------------------------------------------------------------- quote


def build_quote(db, user: User, kitchen_id: int, lines_in: list, strict: bool) -> dict:
    kitchen = db.get(Kitchen, kitchen_id)
    if not kitchen or kitchen.status != "APPROVED":
        raise not_found("Kitchen")
    if user.college_id != kitchen.college_id:
        raise ApiError(403, "COLLEGE_MISMATCH", "You can only order from kitchens in your selected college")
    if not lines_in:
        raise ApiError(400, "EMPTY_CART", "Your cart is empty")

    problems, lines = [], []
    qty_by_item: Counter = Counter()
    for line in lines_in:
        if line.quantity < 1:
            raise ApiError(400, "INVALID_QUANTITY", "Quantity must be at least 1")
        qty_by_item[line.menu_item_id] += line.quantity

    for line in lines_in:
        item = db.get(MenuItem, line.menu_item_id)
        if not item or item.kitchen_id != kitchen_id or item.is_deleted:
            problems.append({"menu_item_id": line.menu_item_id, "code": "ITEM_REMOVED",
                             "message": "This item is no longer on the menu"})
            continue
        problem = None
        if not item.is_available:
            problem = ("SOLD_OUT", f"{item.name} is sold out")
        elif item.stock_qty is not None and item.stock_qty < qty_by_item[item.id]:
            problem = ("SOLD_OUT", f"Only {max(item.stock_qty, 0)} left of {item.name}")
        elif qty_by_item[item.id] > item.max_per_order:
            problem = ("MAX_PER_ORDER", f"Max {item.max_per_order} of {item.name} per order")

        options, unit = [], item.price_paise
        chosen = set(line.choice_ids or [])
        valid_ids = set()
        for group in item.addon_groups:
            picked = [c for c in group.choices if c.id in chosen]
            valid_ids.update(c.id for c in group.choices)
            if len(picked) < group.min_select or len(picked) > group.max_select:
                problem = problem or ("INVALID_OPTIONS",
                                      f"Choose {group.min_select}-{group.max_select} for {group.name}")
            for c in picked:
                if not c.is_available:
                    problem = problem or ("OPTION_UNAVAILABLE", f"{c.name} is unavailable")
                options.append({"group": group.name, "choice_id": c.id, "name": c.name,
                                "price_paise": c.price_paise})
                unit += c.price_paise
        if chosen - valid_ids:
            problem = problem or ("INVALID_OPTIONS", f"Invalid option for {item.name}")

        if problem:
            problems.append({"menu_item_id": item.id, "code": problem[0], "message": problem[1]})
        lines.append({
            "menu_item_id": item.id, "name": item.name, "emoji": item.emoji, "is_veg": item.is_veg,
            "unit_price_paise": unit, "quantity": line.quantity, "options": options,
            "line_total_paise": unit * line.quantity, "ok": problem is None,
        })

    if strict and problems:
        raise ApiError(409, problems[0]["code"], problems[0]["message"], {"problems": problems})

    subtotal = sum(l["line_total_paise"] for l in lines if l["ok"])
    tax = round(subtotal * settings.tax_bps / 10000)
    fee = settings.platform_fee_paise if subtotal else 0
    orderable, closed_reason = kitchen_orderable(kitchen)
    return {
        "kitchen_id": kitchen.id, "kitchen_name": kitchen.name, "lines": lines, "problems": problems,
        "subtotal_paise": subtotal, "tax_paise": tax, "fee_paise": fee, "total_paise": subtotal + tax + fee,
        "can_order": orderable and not problems, "closed_reason": closed_reason,
        "eta_minutes": kitchen.prep_minutes + (10 if kitchen.busy_mode else 0),
    }


# ---------------------------------------------------------------- create


def _reserve_stock(db, qty_by_item: Counter):
    for item_id, qty in sorted(qty_by_item.items()):
        # Conditional decrement: exactly one buyer wins the last portion.
        res = db.execute(
            update(MenuItem)
            .where(MenuItem.id == item_id, MenuItem.stock_qty.is_not(None), MenuItem.stock_qty >= qty)
            .values(stock_qty=MenuItem.stock_qty - qty)
        )
        if res.rowcount == 0:
            limited = db.scalar(select(MenuItem.stock_qty).where(MenuItem.id == item_id))
            if limited is not None:
                raise ApiError(409, "SOLD_OUT", "Sorry, an item just sold out. Please review your cart.")


def _release_stock(db, order: Order):
    qty = Counter()
    for it in order.items:
        qty[it.menu_item_id] += it.quantity
    for item_id, q in qty.items():
        db.execute(update(MenuItem).where(MenuItem.id == item_id, MenuItem.stock_qty.is_not(None))
                   .values(stock_qty=MenuItem.stock_qty + q))


def create_order(db, user: User, body, idempotency_key: str) -> Order:
    existing = db.scalar(select(Order).where(Order.student_id == user.id,
                                             Order.idempotency_key == idempotency_key))
    if existing:
        return existing
    if body.payment_method not in PaymentMethod.ALL:
        raise ApiError(400, "INVALID_PAYMENT_METHOD", "Unsupported payment method")
    if body.payment_method == PaymentMethod.CASH and not flag_enabled(db, "cash_payments"):
        raise ApiError(400, "CASH_DISABLED", "Pay at counter is not available right now")

    kitchen = db.get(Kitchen, body.kitchen_id)
    quote = build_quote(db, user, body.kitchen_id, body.items, strict=True)
    ok, reason = kitchen_orderable(kitchen)
    if not ok:
        raise ApiError(409, "KITCHEN_CLOSED", reason)
    if body.expected_total_paise is not None and body.expected_total_paise != quote["total_paise"]:
        raise ApiError(409, "PRICE_CHANGED", "Prices changed since you opened your cart. Please review.",
                       {"quote": quote})

    try:
        qty = Counter()
        for l in quote["lines"]:
            qty[l["menu_item_id"]] += l["quantity"]
        _reserve_stock(db, qty)

        order = Order(
            student_id=user.id, kitchen_id=kitchen.id, college_id=kitchen.college_id,
            idempotency_key=idempotency_key, payment_method=body.payment_method,
            subtotal_paise=quote["subtotal_paise"], tax_paise=quote["tax_paise"],
            fee_paise=quote["fee_paise"], total_paise=quote["total_paise"],
            instructions=(body.instructions or "")[:300], eta_minutes=quote["eta_minutes"],
        )
        order.items = [
            OrderItem(menu_item_id=l["menu_item_id"], name=l["name"], is_veg=l["is_veg"],
                      unit_price_paise=l["unit_price_paise"], quantity=l["quantity"],
                      options=l["options"], line_total_paise=l["line_total_paise"])
            for l in quote["lines"]
        ]
        db.add(order)
        db.flush()
        order.order_number = f"CB-{1000 + order.id}"
        db.add(Payment(order_id=order.id, method=body.payment_method, amount_paise=order.total_paise))
        db.add(OrderStatusHistory(order_id=order.id, to_status=order.status, actor_id=user.id,
                                  note=f"Order placed ({body.payment_method})"))
        db.flush()
        order_event(db, order, "order_created" if body.payment_method == PaymentMethod.CASH else "order_updated")
        if body.payment_method == PaymentMethod.CASH:
            emit(db, f"kitchen:{kitchen.id}", "new_order", order_id=order.id, order_number=order.order_number)
        db.commit()
    except IntegrityError:
        # Concurrent request with the same idempotency key won the race.
        db.rollback()
        existing = db.scalar(select(Order).where(Order.student_id == user.id,
                                                 Order.idempotency_key == idempotency_key))
        if existing:
            return existing
        raise
    except Exception:
        db.rollback()
        raise
    return order


# ---------------------------------------------------------------- state machine


def is_payable_for_kitchen(order: Order) -> bool:
    """Online orders reach the kitchen only after verified payment."""
    return order.payment_method == PaymentMethod.CASH or order.payment_status == PaymentStatus.PAID


def transition(db, order: Order, to: str, actor_id: int | None, expected_version: int | None,
               note: str | None = None, **fields) -> Order:
    if to not in TRANSITIONS.get(order.status, set()):
        raise ApiError(409, "INVALID_TRANSITION", f"Cannot move order from {order.status} to {to}")
    if expected_version is not None and expected_version != order.version:
        raise ApiError(409, "VERSION_CONFLICT", "This order was updated by someone else. Refreshing.",
                       {"current_version": order.version})
    if to == S.ACCEPTED and not is_payable_for_kitchen(order):
        raise ApiError(409, "PAYMENT_PENDING", "Payment has not been confirmed for this order")

    now = utcnow()
    stamp = {S.ACCEPTED: "accepted_at", S.PREPARING: "preparing_at", S.READY: "ready_at",
             S.COMPLETED: "completed_at", S.REJECTED: "closed_at", S.CANCELLED: "closed_at"}[to]
    fields[stamp] = now
    if to == S.READY:
        fields.update(_new_pickup_fields(order.id))
    if to == S.COMPLETED:
        fields.update(pickup_hash=None, pickup_nonce=None)
    if to in (S.REJECTED, S.CANCELLED):
        fields["reason"] = note

    res = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.version == order.version, Order.status == order.status)
        .values(status=to, version=Order.version + 1, **fields)
    )
    if res.rowcount == 0:
        db.rollback()
        raise ApiError(409, "VERSION_CONFLICT", "This order was updated by someone else. Refreshing.")
    previous = order.status
    db.add(OrderStatusHistory(order_id=order.id, from_status=previous, to_status=to,
                              actor_id=actor_id, note=note))
    db.refresh(order)

    if to in (S.REJECTED, S.CANCELLED):
        _release_stock(db, order)
        _settle_closed_order(db, order, actor_id, note or to.lower())
    if to == S.COMPLETED and order.payment_method == PaymentMethod.CASH:
        _mark_cash_collected(db, order)

    title, body = STUDENT_MESSAGES[to]
    notify(db, order.student_id, title, body.format(
        kitchen=order.kitchen.name, num=order.order_number, eta=order.eta_minutes or "?",
        counter=order.kitchen.counter_location or "the counter", reason=note or "-"), order.id)
    order_event(db, order)
    db.commit()
    return order


def _settle_closed_order(db, order: Order, actor_id, reason: str):
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()))
    if order.payment_status == PaymentStatus.PAID and payment:
        db.add(Refund(payment_id=payment.id, order_id=order.id, amount_paise=payment.amount_paise,
                      reason=reason, actor_id=actor_id))
        order.payment_status = PaymentStatus.REFUND_PENDING
        audit(db, actor_id, "refund.initiated", "order", order.id, amount_paise=payment.amount_paise)
    elif order.payment_status in (PaymentStatus.PENDING, PaymentStatus.FAILED):
        order.payment_status = "VOID"
        if payment:
            payment.status = "VOID"


def _mark_cash_collected(db, order: Order):
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()))
    order.payment_status = PaymentStatus.PAID
    order.paid_at = utcnow()
    if payment:
        payment.status = PaymentStatus.PAID


# ---------------------------------------------------------------- pickup code


def pickup_code(order_id: int, nonce: str) -> str:
    digest = hmac_hex(f"pickup:{order_id}:{nonce}")
    return str(int(digest[:12], 16) % 1_000_000).zfill(6)


def _new_pickup_fields(order_id: int) -> dict:
    nonce = secrets.token_hex(16)
    return {
        "pickup_nonce": nonce,
        "pickup_hash": sha256(f"{order_id}:{pickup_code(order_id, nonce)}"),
        "pickup_expires_at": utcnow() + timedelta(minutes=settings.pickup_code_ttl_minutes),
        "pickup_attempts": 0,
    }


def get_or_rotate_pickup(db, order: Order) -> dict:
    if order.status != S.READY:
        raise ApiError(409, "NOT_READY", "Pickup code is available once your order is ready")
    expired = not order.pickup_expires_at or order.pickup_expires_at < utcnow()
    locked = order.pickup_attempts >= settings.pickup_max_attempts
    if expired or locked or not order.pickup_nonce:
        for k, v in _new_pickup_fields(order.id).items():
            setattr(order, k, v)
        db.commit()
    code = pickup_code(order.id, order.pickup_nonce)
    return {"order_id": order.id, "order_number": order.order_number, "code": code,
            "qr_payload": f"CBPICKUP:{order.id}:{code}",
            "expires_at": order.pickup_expires_at.isoformat() + "Z"}


def verify_pickup(db, order: Order, code: str, actor_id: int) -> Order:
    if order.status != S.READY:
        raise ApiError(409, "NOT_READY", f"Order is {order.status}, not READY")
    if order.pickup_attempts >= settings.pickup_max_attempts:
        raise ApiError(429, "PICKUP_LOCKED", "Too many wrong attempts. Ask the student to refresh their code.")
    if not order.pickup_expires_at or order.pickup_expires_at < utcnow():
        raise ApiError(410, "PICKUP_EXPIRED", "Code expired. Ask the student to reopen their pickup screen.")
    if not order.pickup_hash or not constant_eq(sha256(f"{order.id}:{code.strip()}"), order.pickup_hash):
        db.execute(update(Order).where(Order.id == order.id)
                   .values(pickup_attempts=Order.pickup_attempts + 1))
        audit(db, actor_id, "pickup.failed_attempt", "order", order.id)
        db.commit()
        raise ApiError(400, "INVALID_PICKUP_CODE", "Pickup code does not match")
    audit(db, actor_id, "pickup.verified", "order", order.id)
    return transition(db, order, S.COMPLETED, actor_id, None, note="Pickup verified")
