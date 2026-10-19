"""Kitchen owner / staff app API. Every route checks per-kitchen membership and role."""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..deps import ALL_STAFF, COOKING, FRONT_DESK, MANAGE, Principal, get_principal, kitchen_for_staff
from ..errors import ApiError, not_found
from ..models import (
    AddonChoice,
    AddonGroup,
    Category,
    College,
    Kitchen,
    KitchenClosure,
    KitchenHours,
    KitchenStatus,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    Role,
    User,
    UserRole,
    utcnow,
)
from ..schemas import (
    AcceptIn,
    CategoryIn,
    ClosureIn,
    KitchenRegisterIn,
    KitchenSettingsIn,
    MenuItemIn,
    MenuItemPatch,
    RejectIn,
    StaffIn,
    StatusIn,
    VerifyPickupIn,
    WeeklyHoursIn,
)
from ..services import ordering
from ..services.common import IST, audit, college_out, item_out, kitchen_out, local_now, order_out

router = APIRouter(prefix="/v1", tags=["kitchen"])

_verify_attempts: dict[int, list] = defaultdict(list)  # per-staff throttle for code-only lookup


@router.post("/kitchens/register", status_code=201)
def register_kitchen(body: KitchenRegisterIn, p: Principal = Depends(get_principal),
                     db: DbSession = Depends(get_db)):
    college = db.get(College, body.college_id)
    if not college or not college.is_active:
        raise ApiError(400, "INVALID_COLLEGE", "Choose an active college")
    dup = db.scalar(select(Kitchen).where(Kitchen.college_id == college.id,
                                          func.lower(Kitchen.name) == body.name.strip().lower()))
    if dup:
        raise ApiError(409, "DUPLICATE_KITCHEN", "A kitchen with this name already exists at this college")
    if body.owner_name and not p.user.name:
        p.user.name = body.owner_name
    k = Kitchen(college_id=college.id, owner_id=p.id, name=body.name.strip(), description=body.description,
                cuisine=body.cuisine, counter_location=body.counter_location, fssai_number=body.fssai_number,
                status=KitchenStatus.PENDING)
    db.add(k)
    db.flush()
    db.add(UserRole(user_id=p.id, role=Role.KITCHEN_OWNER, kitchen_id=k.id))
    audit(db, p.id, "kitchen.registered", "kitchen", k.id, name=k.name, college_id=college.id)
    db.commit()
    return kitchen_out(k, private=True)


@router.get("/kitchen/me")
def my_kitchens(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    out = []
    for kid in sorted(p.kitchen_ids()):
        k = db.get(Kitchen, kid)
        d = kitchen_out(k, private=True)
        d["my_role"] = p.kitchen_role(kid)
        d["college"] = college_out(k.college)
        out.append(d)
    return {"items": out}


@router.get("/kitchen/kitchens/{kid}")
def get_kitchen(kid: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    k = kitchen_for_staff(db, p, kid, ALL_STAFF)
    d = kitchen_out(k, private=True)
    d["my_role"] = p.kitchen_role(kid)
    return d


@router.patch("/kitchen/kitchens/{kid}")
def update_kitchen(kid: int, body: KitchenSettingsIn, p: Principal = Depends(get_principal),
                   db: DbSession = Depends(get_db)):
    k = kitchen_for_staff(db, p, kid, MANAGE)
    changes = body.model_dump(exclude_unset=True)
    for key, v in changes.items():
        setattr(k, key, v)
    audit(db, p.id, "kitchen.settings_updated", "kitchen", k.id, **changes)
    db.commit()
    return kitchen_out(k, private=True)


@router.put("/kitchen/kitchens/{kid}/hours")
def set_weekly_hours(kid: int, body: WeeklyHoursIn, p: Principal = Depends(get_principal),
                     db: DbSession = Depends(get_db)):
    k = kitchen_for_staff(db, p, kid, MANAGE)
    if sorted(d.weekday for d in body.days) != list(range(7)):
        raise ApiError(400, "INVALID_HOURS", "Provide each weekday exactly once")
    existing = {h.weekday: h for h in k.hours}
    for d in body.days:
        row = existing.get(d.weekday)
        if row is None:
            k.hours.append(KitchenHours(**d.model_dump()))
        else:
            row.opens_at, row.closes_at, row.is_closed = d.opens_at, d.closes_at, d.is_closed
    audit(db, p.id, "kitchen.hours_updated", "kitchen", k.id, days=[d.model_dump() for d in body.days])
    db.commit()
    db.refresh(k)
    return kitchen_out(k, private=True)


@router.post("/kitchen/kitchens/{kid}/closures", status_code=201)
def add_closure(kid: int, body: ClosureIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    k = kitchen_for_staff(db, p, kid, MANAGE)
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise ApiError(400, "INVALID_DATE", "Invalid date")
    if body.date < local_now().strftime("%Y-%m-%d"):
        raise ApiError(400, "PAST_DATE", "Choose today or a future date")
    if any(c.date == body.date for c in k.closures):
        raise ApiError(409, "DUPLICATE_CLOSURE", "This date is already marked closed")
    k.closures.append(KitchenClosure(date=body.date, reason=body.reason.strip()))
    audit(db, p.id, "kitchen.closure_added", "kitchen", k.id, date=body.date, reason=body.reason)
    db.commit()
    db.refresh(k)
    return kitchen_out(k, private=True)


@router.delete("/kitchen/kitchens/{kid}/closures/{closure_id}")
def remove_closure(kid: int, closure_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    k = kitchen_for_staff(db, p, kid, MANAGE)
    c = db.get(KitchenClosure, closure_id)
    if not c or c.kitchen_id != k.id:
        raise not_found("Closure")
    db.delete(c)
    audit(db, p.id, "kitchen.closure_removed", "kitchen", k.id, date=c.date)
    db.commit()
    db.refresh(k)
    return kitchen_out(k, private=True)


# ---------------------------------------------------------------- menu


@router.get("/kitchen/kitchens/{kid}/menu")
def staff_menu(kid: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, ALL_STAFF)
    cats = db.scalars(select(Category).where(Category.kitchen_id == kid)
                      .order_by(Category.sort_order, Category.id)).all()
    items = db.scalars(select(MenuItem).where(MenuItem.kitchen_id == kid, MenuItem.is_deleted.is_(False))
                       .order_by(MenuItem.id)).all()
    return {"categories": [{"id": c.id, "name": c.name, "sort_order": c.sort_order} for c in cats],
            "items": [item_out(i, private=True) for i in items]}


@router.post("/kitchen/kitchens/{kid}/categories", status_code=201)
def add_category(kid: int, body: CategoryIn, p: Principal = Depends(get_principal),
                 db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, MANAGE)
    c = Category(kitchen_id=kid, name=body.name.strip(), sort_order=body.sort_order)
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "sort_order": c.sort_order}


def _own_category(db, kid: int, category_id: int | None):
    if category_id is None:
        return
    c = db.get(Category, category_id)
    if not c or c.kitchen_id != kid:
        raise ApiError(400, "INVALID_CATEGORY", "Category does not belong to this kitchen")


@router.patch("/kitchen/categories/{cid}")
def edit_category(cid: int, body: CategoryIn, p: Principal = Depends(get_principal),
                  db: DbSession = Depends(get_db)):
    c = db.get(Category, cid)
    if not c:
        raise not_found("Category")
    kitchen_for_staff(db, p, c.kitchen_id, MANAGE)
    c.name, c.sort_order = body.name.strip(), body.sort_order
    db.commit()
    return {"id": c.id, "name": c.name, "sort_order": c.sort_order}


@router.delete("/kitchen/categories/{cid}")
def delete_category(cid: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    c = db.get(Category, cid)
    if not c:
        raise not_found("Category")
    kitchen_for_staff(db, p, c.kitchen_id, MANAGE)
    db.delete(c)  # items keep existing with category_id = NULL
    db.commit()
    return {"ok": True}


def _set_addons(item: MenuItem, groups):
    if any(g.min_select > g.max_select for g in groups):
        raise ApiError(400, "INVALID_OPTIONS", "min_select cannot exceed max_select")
    item.addon_groups = [
        AddonGroup(name=g.name, min_select=g.min_select, max_select=g.max_select,
                   choices=[AddonChoice(**c.model_dump()) for c in g.choices])
        for g in groups
    ]


@router.post("/kitchen/kitchens/{kid}/menu-items", status_code=201)
def add_item(kid: int, body: MenuItemIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, MANAGE)
    _own_category(db, kid, body.category_id)
    data = body.model_dump(exclude={"addon_groups"})
    data["name"] = data["name"].strip()
    item = MenuItem(kitchen_id=kid, **data)
    _set_addons(item, body.addon_groups)
    db.add(item)
    db.flush()
    audit(db, p.id, "menu.item_created", "menu_item", item.id, name=item.name, price_paise=item.price_paise)
    db.commit()
    return item_out(item, private=True)


def _staff_item(db, p, item_id: int, allowed) -> MenuItem:
    item = db.get(MenuItem, item_id)
    if not item or item.is_deleted:
        raise not_found("Item")
    kitchen_for_staff(db, p, item.kitchen_id, allowed)
    return item


@router.patch("/kitchen/menu-items/{item_id}")
def edit_item(item_id: int, body: MenuItemPatch, p: Principal = Depends(get_principal),
              db: DbSession = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    # Cooks/cashiers may only flip availability and stock; everything else needs a manager.
    stock_only = set(data) <= {"is_available", "stock_qty", "unlimited_stock"}
    item = _staff_item(db, p, item_id, ALL_STAFF if stock_only else MANAGE)
    if "category_id" in data:
        _own_category(db, item.kitchen_id, data["category_id"])
    groups = data.pop("addon_groups", None)
    if data.pop("unlimited_stock", False):
        data["stock_qty"] = None
    before = {k: getattr(item, k) for k in data}
    for k, v in data.items():
        setattr(item, k, v)
    if groups is not None:
        _set_addons(item, body.addon_groups)
    audit(db, p.id, "menu.item_updated", "menu_item", item.id, before=before, after=data)
    db.commit()
    db.refresh(item)
    return item_out(item, private=True)


@router.delete("/kitchen/menu-items/{item_id}")
def delete_item(item_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    item = _staff_item(db, p, item_id, MANAGE)
    item.is_deleted = True  # soft delete keeps order history intact
    audit(db, p.id, "menu.item_deleted", "menu_item", item.id)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- orders


@router.get("/kitchen/kitchens/{kid}/orders")
def kitchen_orders(kid: int, status: str | None = None, p: Principal = Depends(get_principal),
                   db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, ALL_STAFF)
    stmt = select(Order).where(Order.kitchen_id == kid)
    # Online orders reach the kitchen only after verified payment.
    payable = (Order.payment_method == PaymentMethod.CASH) | Order.payment_status.not_in(
        (PaymentStatus.PENDING, PaymentStatus.FAILED))
    stmt = stmt.where(payable | (Order.status != OrderStatus.PENDING_ACCEPTANCE))
    if status == "COMPLETED":
        since = utcnow() - timedelta(hours=24)
        stmt = stmt.where(Order.status.in_(OrderStatus.FINAL), Order.created_at > since).order_by(Order.id.desc())
    elif status:
        stmt = stmt.where(Order.status == status).order_by(Order.id)
    else:
        stmt = stmt.where(Order.status.in_(OrderStatus.ACTIVE)).order_by(Order.id)
    orders = db.scalars(stmt.limit(200)).all()
    counts = dict(db.execute(select(Order.status, func.count()).where(
        Order.kitchen_id == kid, Order.status.in_(OrderStatus.ACTIVE),
        payable | (Order.status != OrderStatus.PENDING_ACCEPTANCE)).group_by(Order.status)).all())
    return {"items": [order_out(o, include_student=True) for o in orders], "counts": counts}


def _staff_order(db, p, order_id: int, allowed) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise not_found("Order")
    kitchen_for_staff(db, p, order.kitchen_id, allowed)
    return order


@router.post("/kitchen/orders/{order_id}/accept")
def accept(order_id: int, body: AcceptIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    order = _staff_order(db, p, order_id, FRONT_DESK)
    fields = {"eta_minutes": body.eta_minutes} if body.eta_minutes else {}
    order = ordering.transition(db, order, OrderStatus.ACCEPTED, p.id, body.version, **fields)
    return order_out(order, include_student=True)


@router.post("/kitchen/orders/{order_id}/reject")
def reject(order_id: int, body: RejectIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    order = _staff_order(db, p, order_id, FRONT_DESK)
    order = ordering.transition(db, order, OrderStatus.REJECTED, p.id, body.version, note=body.reason)
    return order_out(order, include_student=True)


@router.patch("/kitchen/orders/{order_id}/status")
def set_status(order_id: int, body: StatusIn, p: Principal = Depends(get_principal),
               db: DbSession = Depends(get_db)):
    order = _staff_order(db, p, order_id, COOKING)
    order = ordering.transition(db, order, body.status, p.id, body.version)
    return order_out(order, include_student=True)


@router.post("/kitchen/orders/{order_id}/cancel")
def kitchen_cancel(order_id: int, body: RejectIn, p: Principal = Depends(get_principal),
                   db: DbSession = Depends(get_db)):
    order = _staff_order(db, p, order_id, MANAGE)
    order = ordering.transition(db, order, OrderStatus.CANCELLED, p.id, body.version, note=body.reason)
    return order_out(order, include_student=True)


@router.post("/kitchen/kitchens/{kid}/verify-pickup")
def verify_pickup(kid: int, body: VerifyPickupIn, p: Principal = Depends(get_principal),
                  db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, FRONT_DESK)
    code, order_id = body.code.strip(), body.order_id
    if code.startswith("CBPICKUP:"):  # scanned QR payload
        try:
            _, oid, code = code.split(":")
            order_id = int(oid)
        except ValueError:
            raise ApiError(400, "INVALID_PICKUP_CODE", "Unrecognised QR code")
    if order_id is not None:
        order = db.get(Order, order_id)
        if not order or order.kitchen_id != kid:
            raise ApiError(400, "INVALID_PICKUP_CODE", "This order does not belong to your kitchen")
        return order_out(ordering.verify_pickup(db, order, code, p.id), include_student=True)

    # Code-only lookup across READY orders of this kitchen, throttled per staff member.
    now = utcnow()
    recent = [t for t in _verify_attempts[p.id] if t > now - timedelta(minutes=1)]
    if len(recent) >= 10:
        raise ApiError(429, "TOO_MANY_ATTEMPTS", "Too many attempts. Wait a minute.")
    _verify_attempts[p.id] = recent + [now]
    from ..security import sha256
    ready = db.scalars(select(Order).where(Order.kitchen_id == kid, Order.status == OrderStatus.READY)).all()
    match = [o for o in ready if o.pickup_hash == sha256(f"{o.id}:{code}")]
    if len(match) != 1:
        raise ApiError(400, "INVALID_PICKUP_CODE", "No ready order matches this code")
    return order_out(ordering.verify_pickup(db, match[0], code, p.id), include_student=True)


# ---------------------------------------------------------------- staff


@router.get("/kitchen/kitchens/{kid}/staff")
def list_staff(kid: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, MANAGE)
    rows = db.execute(select(UserRole, User).join(User, User.id == UserRole.user_id)
                      .where(UserRole.kitchen_id == kid)).all()
    return {"items": [{"user_id": u.id, "name": u.name, "phone": u.phone, "role": r.role,
                       "is_active": u.is_active} for r, u in rows]}


@router.post("/kitchen/kitchens/{kid}/staff", status_code=201)
def add_staff(kid: int, body: StaffIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, (Role.KITCHEN_OWNER,) if body.role == Role.KITCHEN_MANAGER else MANAGE)
    user = db.scalar(select(User).where(User.phone == body.phone))
    if not user:
        user = User(phone=body.phone, name=body.name)
        db.add(user)
        db.flush()
    existing = db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.kitchen_id == kid))
    if existing:
        if existing.role == Role.KITCHEN_OWNER:
            raise ApiError(409, "IS_OWNER", "This person owns the kitchen")
        existing.role = body.role
    else:
        db.add(UserRole(user_id=user.id, role=body.role, kitchen_id=kid))
    audit(db, p.id, "staff.added", "kitchen", kid, user_id=user.id, role=body.role)
    db.commit()
    return {"user_id": user.id, "name": user.name, "phone": user.phone, "role": body.role}


@router.delete("/kitchen/kitchens/{kid}/staff/{user_id}")
def remove_staff(kid: int, user_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, MANAGE)
    role = db.scalar(select(UserRole).where(UserRole.user_id == user_id, UserRole.kitchen_id == kid))
    if not role:
        raise not_found("Staff member")
    if role.role == Role.KITCHEN_OWNER:
        raise ApiError(409, "IS_OWNER", "The owner cannot be removed")
    db.delete(role)  # takes effect on the next request: roles are re-read every time
    audit(db, p.id, "staff.removed", "kitchen", kid, user_id=user_id)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- reports


@router.get("/kitchen/kitchens/{kid}/reports")
def reports(kid: int, days: int = 7, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    kitchen_for_staff(db, p, kid, MANAGE)
    days = min(max(days, 1), 90)
    since = utcnow() - timedelta(days=days)
    orders = db.scalars(select(Order).where(Order.kitchen_id == kid, Order.created_at > since)).all()
    completed = [o for o in orders if o.status == OrderStatus.COMPLETED]
    gmv = sum(o.subtotal_paise for o in completed)
    tax = sum(o.tax_paise for o in completed)
    commission = round(gmv * settings.commission_bps / 10000)
    refunds = sum(o.total_paise for o in orders if o.payment_status in ("REFUND_PENDING", "REFUNDED"))

    by_day: dict[str, dict] = {}
    by_hour = [0] * 24
    for o in completed:
        local = o.created_at.replace(tzinfo=None) + timedelta(hours=5, minutes=30)
        d = by_day.setdefault(local.strftime("%Y-%m-%d"), {"date": local.strftime("%Y-%m-%d"),
                                                             "orders": 0, "sales_paise": 0})
        d["orders"] += 1
        d["sales_paise"] += o.subtotal_paise
        by_hour[local.hour] += 1

    top = db.execute(select(OrderItem.name, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total_paise))
                     .join(Order, Order.id == OrderItem.order_id)
                     .where(Order.kitchen_id == kid, Order.status == OrderStatus.COMPLETED,
                            Order.created_at > since)
                     .group_by(OrderItem.name).order_by(func.sum(OrderItem.quantity).desc()).limit(8)).all()
    prep = [(o.ready_at - o.accepted_at).total_seconds() / 60 for o in completed if o.ready_at and o.accepted_at]
    prep.sort()
    return {
        "days": days,
        "completed_orders": len(completed),
        "cancelled_orders": sum(1 for o in orders if o.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED)),
        "gross_sales_paise": gmv,
        "tax_paise": tax,
        "platform_commission_paise": commission,
        "net_payout_paise": gmv - commission,
        "refunds_paise": refunds,
        "avg_order_paise": round(gmv / len(completed)) if completed else 0,
        "prep_p50_min": round(prep[len(prep) // 2], 1) if prep else None,
        "prep_p90_min": round(prep[int(len(prep) * 0.9)], 1) if prep else None,
        "by_day": sorted(by_day.values(), key=lambda d: d["date"]),
        "by_hour": [{"hour": h, "orders": n} for h, n in enumerate(by_hour)],
        "top_items": [{"name": n, "quantity": int(q), "sales_paise": int(s)} for n, q, s in top],
        "timezone": str(IST),
    }
