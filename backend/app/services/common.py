from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..models import (
    AuditLog,
    College,
    FeatureFlag,
    Kitchen,
    MenuItem,
    Notification,
    Order,
    User,
)
from ..realtime import emit

IST = timezone(timedelta(hours=5, minutes=30))


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def audit(db, actor_id: int | None, action: str, entity: str, entity_id=None, **detail):
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity,
                    entity_id=str(entity_id) if entity_id is not None else None, detail=detail))


def notify(db, user_id: int, title: str, body: str, order_id: int | None = None):
    db.add(Notification(user_id=user_id, title=title, body=body, order_id=order_id))
    emit(db, f"user:{user_id}", "notification", title=title, body=body, order_id=order_id)


def paginate(db, stmt, page: int, size: int, serialize):
    page, size = max(page, 1), min(max(size, 1), 100)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return {"items": [serialize(r) for r in rows], "page": page, "size": size, "total": total}


def flag_enabled(db, key: str, default: bool = True) -> bool:
    flag = db.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
    return flag.enabled if flag else default


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def local_now(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(IST)


def day_schedule(k: Kitchen, day: datetime) -> tuple[str | None, str | None, str | None]:
    """(opens_at, closes_at, closed_reason) for a campus-local date."""
    closure = next((c for c in k.closures if c.date == day.strftime("%Y-%m-%d")), None)
    if closure:
        return None, None, closure.reason
    row = next((h for h in k.hours if h.weekday == day.weekday()), None)
    if row:
        return (None, None, "Closed today") if row.is_closed else (row.opens_at, row.closes_at, None)
    return k.opens_at, k.closes_at, None


def next_opening(k: Kitchen, now: datetime | None = None) -> str | None:
    local = local_now(now)
    for offset in range(8):
        day = local + timedelta(days=offset)
        opens, _, _ = day_schedule(k, day)
        if opens and (offset or opens > local.strftime("%H:%M")):
            label = "today" if offset == 0 else "tomorrow" if offset == 1 else WEEKDAYS[day.weekday()]
            return f"{label} at {opens}"
    return None


def kitchen_open_now(k: Kitchen, now: datetime | None = None) -> bool:
    local = local_now(now)
    hhmm = local.strftime("%H:%M")
    opens, closes, _ = day_schedule(k, local)
    if opens and (opens <= hhmm < closes if opens <= closes else hhmm >= opens):
        return True
    # Overnight window that started yesterday (e.g. 18:00–02:00).
    y_opens, y_closes, _ = day_schedule(k, local - timedelta(days=1))
    return bool(y_opens and y_opens > y_closes and hhmm < y_closes)


def kitchen_orderable(k: Kitchen) -> tuple[bool, str | None]:
    if k.status != "APPROVED":
        return False, "This kitchen is not available"
    if not k.is_accepting:
        return False, "Kitchen is not accepting orders right now"
    if not kitchen_open_now(k):
        _, _, reason = day_schedule(k, local_now())
        nxt = next_opening(k)
        return False, f"{reason or 'Kitchen is closed'}. Opens {nxt}" if nxt else (reason or "Kitchen is closed")
    return True, None


# ---------------------------------------------------------------- serializers


def user_out(u: User, roles=None) -> dict:
    out = {
        "id": u.id, "phone": u.phone, "name": u.name, "email": u.email, "roll_no": u.roll_no,
        "year": u.year, "college_id": u.college_id, "is_active": u.is_active,
        "is_flagged": u.is_flagged, "created_at": iso(u.created_at),
    }
    if roles is not None:
        out["roles"] = [{"role": r.role, "kitchen_id": r.kitchen_id, "college_id": r.college_id} for r in roles]
    return out


def college_out(c: College, distance_km: float | None = None) -> dict:
    return {
        "id": c.id, "name": c.name, "code": c.code, "city": c.city, "address": c.address,
        "lat": c.lat, "lng": c.lng, "contact_name": c.contact_name, "contact_phone": c.contact_phone,
        "is_active": c.is_active,
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
    }


def weekly_hours(k: Kitchen) -> list[dict]:
    rows = {h.weekday: h for h in k.hours}
    return [
        {"weekday": d, "day": WEEKDAYS[d],
         "opens_at": rows[d].opens_at if d in rows else k.opens_at,
         "closes_at": rows[d].closes_at if d in rows else k.closes_at,
         "is_closed": rows[d].is_closed if d in rows else False}
        for d in range(7)
    ]


def kitchen_out(k: Kitchen, private: bool = False) -> dict:
    is_open, closed_reason = kitchen_orderable(k)
    today_opens, today_closes, _ = day_schedule(k, local_now())
    out = {
        "id": k.id, "college_id": k.college_id, "name": k.name, "description": k.description,
        "cuisine": k.cuisine, "counter_location": k.counter_location, "emoji": k.emoji,
        "is_open": is_open, "closed_reason": closed_reason, "busy_mode": k.busy_mode,
        "prep_minutes": k.prep_minutes + (10 if k.busy_mode else 0),
        "opens_at": today_opens, "closes_at": today_closes,  # today's window; None if closed today
        "rating": round(k.rating_sum / k.rating_count, 1) if k.rating_count else None,
        "rating_count": k.rating_count,
    }
    if private:
        out.update(status=k.status, status_reason=k.status_reason, is_accepting=k.is_accepting,
                   base_prep_minutes=k.prep_minutes, owner_id=k.owner_id, fssai_number=k.fssai_number,
                   created_at=iso(k.created_at), default_opens_at=k.opens_at, default_closes_at=k.closes_at,
                   weekly_hours=weekly_hours(k),
                   closures=[{"id": c.id, "date": c.date, "reason": c.reason} for c in k.closures
                             if c.date >= local_now().strftime("%Y-%m-%d")])
    return out


def item_out(i: MenuItem, private: bool = False) -> dict:
    sold_out = (not i.is_available) or (i.stock_qty is not None and i.stock_qty <= 0)
    out = {
        "id": i.id, "kitchen_id": i.kitchen_id, "category_id": i.category_id, "sku": i.sku,
        "name": i.name, "description": i.description, "price_paise": i.price_paise,
        "is_veg": i.is_veg, "emoji": i.emoji, "image_url": i.image_url, "sold_out": sold_out,
        "max_per_order": i.max_per_order, "is_popular": i.is_popular,
        "addon_groups": [
            {
                "id": g.id, "name": g.name, "min_select": g.min_select, "max_select": g.max_select,
                "choices": [
                    {"id": c.id, "name": c.name, "price_paise": c.price_paise, "is_available": c.is_available}
                    for c in g.choices
                ],
            }
            for g in i.addon_groups
        ],
    }
    if private:
        out.update(is_available=i.is_available, stock_qty=i.stock_qty, updated_at=iso(i.updated_at))
    return out


def order_out(o: Order, include_student: bool = False) -> dict:
    out = {
        "id": o.id, "order_number": o.order_number, "status": o.status,
        "payment_status": o.payment_status, "payment_method": o.payment_method,
        "kitchen": {"id": o.kitchen.id, "name": o.kitchen.name, "emoji": o.kitchen.emoji,
                    "counter_location": o.kitchen.counter_location},
        "college_id": o.college_id,
        "items": [
            {"menu_item_id": it.menu_item_id, "name": it.name, "is_veg": it.is_veg,
             "unit_price_paise": it.unit_price_paise, "quantity": it.quantity,
             "options": it.options, "line_total_paise": it.line_total_paise}
            for it in o.items
        ],
        "subtotal_paise": o.subtotal_paise, "tax_paise": o.tax_paise, "fee_paise": o.fee_paise,
        "total_paise": o.total_paise, "instructions": o.instructions, "eta_minutes": o.eta_minutes,
        "reason": o.reason, "version": o.version, "rating": o.rating,
        "pickup_expires_at": iso(o.pickup_expires_at),
        "created_at": iso(o.created_at), "paid_at": iso(o.paid_at), "accepted_at": iso(o.accepted_at),
        "preparing_at": iso(o.preparing_at), "ready_at": iso(o.ready_at),
        "completed_at": iso(o.completed_at), "closed_at": iso(o.closed_at),
        "ack_overdue": o.ack_overdue_flagged and o.status == "PENDING_ACCEPTANCE",
    }
    if include_student:
        # Staff sees only what is needed to hand over the meal.
        out["student"] = {"id": o.student.id, "name": o.student.name or "Student",
                          "phone_last4": o.student.phone[-4:]}
    return out
