"""Super admin / college admin operations. College admins are scoped to their colleges;
mutations that affect money or platform config require super admin."""
import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..deps import Principal, admin_college_scope, require_admin, require_super_admin
from ..errors import ApiError, not_found
from ..models import (
    AuditLog,
    College,
    FeatureFlag,
    Kitchen,
    KitchenStatus,
    Order,
    OrderStatus,
    Payment,
    Refund,
    SupportTicket,
    User,
    UserRole,
    utcnow,
)
from ..schemas import CollegeIn, CollegePatch, FlagPatch, ReasonIn, TicketPatch, UserPatch
from ..services import ordering
from ..services.common import audit, college_out, iso, kitchen_out, notify, order_out, paginate, user_out
from .student import ticket_out

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _scoped(stmt, column, p: Principal):
    scope = admin_college_scope(p)
    return stmt if scope is None else stmt.where(column.in_(scope or {-1}))


def _check_college(p: Principal, college_id: int):
    scope = admin_college_scope(p)
    if scope is not None and college_id not in scope:
        raise not_found("Resource")


# ---------------------------------------------------------------- dashboard


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    today = utcnow() - timedelta(hours=24)
    orders = _scoped(select(Order), Order.college_id, p)
    recent = db.scalars(orders.where(Order.created_at > today)).all()
    completed = [o for o in recent if o.status == OrderStatus.COMPLETED]
    gmv = sum(o.subtotal_paise for o in completed)
    by_status: dict[str, int] = {}
    for o in recent:
        by_status[o.status] = by_status.get(o.status, 0) + 1
    week = utcnow() - timedelta(days=7)
    series = db.execute(_scoped(
        select(func.date(Order.created_at), func.count(), func.sum(Order.subtotal_paise))
        .where(Order.created_at > week, Order.status == OrderStatus.COMPLETED), Order.college_id, p)
        .group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at))).all()
    active_students = len({o.student_id for o in recent})
    return {
        "orders_24h": len(recent),
        "completed_24h": len(completed),
        "gmv_24h_paise": gmv,
        "commission_24h_paise": round(gmv * settings.commission_bps / 10000),
        "active_students_24h": active_students,
        "by_status_24h": by_status,
        "live_orders": db.scalar(_scoped(select(func.count(Order.id)).where(
            Order.status.in_(OrderStatus.ACTIVE)), Order.college_id, p)),
        "delayed_orders": db.scalar(_scoped(select(func.count(Order.id)).where(
            Order.ack_overdue_flagged.is_(True), Order.status == OrderStatus.PENDING_ACCEPTANCE),
            Order.college_id, p)),
        "pending_kitchens": db.scalar(_scoped(select(func.count(Kitchen.id)).where(
            Kitchen.status == KitchenStatus.PENDING), Kitchen.college_id, p)),
        "open_tickets": db.scalar(select(func.count(SupportTicket.id)).where(SupportTicket.status != "RESOLVED")),
        "colleges": db.scalar(_scoped(select(func.count(College.id)), College.id, p)),
        "kitchens": db.scalar(_scoped(select(func.count(Kitchen.id)).where(
            Kitchen.status == KitchenStatus.APPROVED), Kitchen.college_id, p)),
        "students": db.scalar(_scoped(select(func.count(User.id)).where(User.college_id.is_not(None)),
                                      User.college_id, p)),
        "series_7d": [{"date": str(d), "orders": n, "gmv_paise": int(s or 0)} for d, n, s in series],
    }


# ---------------------------------------------------------------- colleges


@router.get("/colleges")
def colleges(p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    rows = db.scalars(_scoped(select(College), College.id, p).order_by(College.name)).all()
    out = []
    for c in rows:
        d = college_out(c)
        d["kitchen_count"] = db.scalar(select(func.count(Kitchen.id)).where(Kitchen.college_id == c.id))
        d["student_count"] = db.scalar(select(func.count(User.id)).where(User.college_id == c.id))
        out.append(d)
    return {"items": out}


@router.post("/colleges", status_code=201)
def create_college(body: CollegeIn, p: Principal = Depends(require_super_admin), db: DbSession = Depends(get_db)):
    if db.scalar(select(College).where(func.upper(College.code) == body.code.upper())):
        raise ApiError(409, "DUPLICATE_CODE", "College code already exists", {"code": "Already used"})
    c = College(**{**body.model_dump(), "code": body.code.upper()})
    db.add(c)
    db.flush()
    audit(db, p.id, "college.created", "college", c.id, name=c.name)
    db.commit()
    return college_out(c)


@router.patch("/colleges/{cid}")
def update_college(cid: int, body: CollegePatch, p: Principal = Depends(require_super_admin),
                   db: DbSession = Depends(get_db)):
    c = db.get(College, cid)
    if not c:
        raise not_found("College")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    audit(db, p.id, "college.updated", "college", c.id, **changes)
    db.commit()
    return college_out(c)


# ---------------------------------------------------------------- kitchens


@router.get("/kitchens")
def kitchens(status: str | None = None, college_id: int | None = None, q: str = "", page: int = 1,
             size: int = 50, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    stmt = _scoped(select(Kitchen), Kitchen.college_id, p)
    if status:
        stmt = stmt.where(Kitchen.status == status)
    if college_id:
        stmt = stmt.where(Kitchen.college_id == college_id)
    if q:
        stmt = stmt.where(Kitchen.name.ilike(f"%{q}%"))

    def ser(k: Kitchen):
        d = kitchen_out(k, private=True)
        owner = db.get(User, k.owner_id)
        d["owner"] = {"id": owner.id, "name": owner.name, "phone": owner.phone}
        d["college_name"] = k.college.name
        return d

    return paginate(db, stmt.order_by(Kitchen.id.desc()), page, size, ser)


def _moderate(db, p: Principal, kid: int, status: str, reason: str | None, action: str):
    k = db.get(Kitchen, kid)
    if not k:
        raise not_found("Kitchen")
    _check_college(p, k.college_id)
    k.status, k.status_reason = status, reason
    audit(db, p.id, action, "kitchen", k.id, reason=reason)
    notify(db, k.owner_id, f"Kitchen {status.lower()}",
           f"{k.name}: {reason}" if reason else f"{k.name} is now {status.lower()}.")
    db.commit()
    return kitchen_out(k, private=True)


@router.post("/kitchens/{kid}/approve")
def approve(kid: int, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    return _moderate(db, p, kid, KitchenStatus.APPROVED, None, "kitchen.approved")


@router.post("/kitchens/{kid}/reject")
def reject(kid: int, body: ReasonIn, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    return _moderate(db, p, kid, KitchenStatus.REJECTED, body.reason, "kitchen.rejected")


@router.post("/kitchens/{kid}/suspend")
def suspend(kid: int, body: ReasonIn, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    return _moderate(db, p, kid, KitchenStatus.SUSPENDED, body.reason, "kitchen.suspended")


# ---------------------------------------------------------------- students / users


@router.get("/users")
def users(q: str = "", college_id: int | None = None, flagged: bool | None = None, page: int = 1,
          size: int = 50, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    stmt = _scoped(select(User), User.college_id, p)
    if q:
        stmt = stmt.where(or_(User.phone.ilike(f"%{q}%"), User.name.ilike(f"%{q}%"),
                              User.roll_no.ilike(f"%{q}%")))
    if college_id:
        stmt = stmt.where(User.college_id == college_id)
    if flagged is not None:
        stmt = stmt.where(User.is_flagged.is_(flagged))

    def ser(u: User):
        d = user_out(u, db.scalars(select(UserRole).where(UserRole.user_id == u.id)).all())
        d["order_count"] = db.scalar(select(func.count(Order.id)).where(Order.student_id == u.id))
        return d

    return paginate(db, stmt.order_by(User.id.desc()), page, size, ser)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserPatch, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise not_found("User")
    if u.college_id:
        _check_college(p, u.college_id)
    changes = body.model_dump(exclude_unset=True, exclude={"note"})
    if u.id == p.id and changes.get("is_active") is False:
        raise ApiError(400, "SELF_SUSPEND", "You cannot suspend yourself")
    for k, v in changes.items():
        setattr(u, k, v)
    audit(db, p.id, "user.updated", "user", u.id, note=body.note, **changes)
    db.commit()
    return user_out(u)


# ---------------------------------------------------------------- orders / money


def _order_filters(stmt, college_id, kitchen_id, status, payment_status, q):
    if college_id:
        stmt = stmt.where(Order.college_id == college_id)
    if kitchen_id:
        stmt = stmt.where(Order.kitchen_id == kitchen_id)
    if status == "DELAYED":
        stmt = stmt.where(Order.ack_overdue_flagged.is_(True), Order.status == OrderStatus.PENDING_ACCEPTANCE)
    elif status == "ACTIVE":
        stmt = stmt.where(Order.status.in_(OrderStatus.ACTIVE))
    elif status:
        stmt = stmt.where(Order.status == status)
    if payment_status:
        stmt = stmt.where(Order.payment_status == payment_status)
    if q:
        stmt = stmt.where(Order.order_number.ilike(f"%{q}%"))
    return stmt


@router.get("/orders")
def orders(college_id: int | None = None, kitchen_id: int | None = None, status: str | None = None,
           payment_status: str | None = None, q: str = "", page: int = 1, size: int = 25,
           p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    stmt = _order_filters(_scoped(select(Order), Order.college_id, p),
                          college_id, kitchen_id, status, payment_status, q)
    return paginate(db, stmt.order_by(Order.id.desc()), page, size, lambda o: order_out(o, include_student=True))


@router.get("/orders/{oid}/history")
def order_history(oid: int, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    from ..models import OrderStatusHistory
    o = db.get(Order, oid)
    if not o:
        raise not_found("Order")
    _check_college(p, o.college_id)
    rows = db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == oid)
                      .order_by(OrderStatusHistory.id)).all()
    pays = db.scalars(select(Payment).where(Payment.order_id == oid)).all()
    refunds = db.scalars(select(Refund).where(Refund.order_id == oid)).all()
    return {
        "order": order_out(o, include_student=True),
        "history": [{"from": h.from_status, "to": h.to_status, "actor_id": h.actor_id, "note": h.note,
                     "at": iso(h.created_at)} for h in rows],
        "payments": [{"id": x.id, "method": x.method, "amount_paise": x.amount_paise, "status": x.status,
                      "provider_ref": x.provider_ref, "at": iso(x.created_at)} for x in pays],
        "refunds": [{"id": r.id, "amount_paise": r.amount_paise, "status": r.status, "reason": r.reason,
                     "at": iso(r.created_at)} for r in refunds],
    }


@router.post("/orders/{oid}/cancel")
def admin_cancel(oid: int, body: ReasonIn, p: Principal = Depends(require_super_admin),
                 db: DbSession = Depends(get_db)):
    o = db.get(Order, oid)
    if not o:
        raise not_found("Order")
    audit(db, p.id, "order.admin_cancel", "order", o.id, reason=body.reason)
    return order_out(ordering.transition(db, o, OrderStatus.CANCELLED, p.id, None,
                                         note=f"Cancelled by CampusBite: {body.reason}"), include_student=True)


@router.get("/payments")
def payments(status: str | None = None, page: int = 1, size: int = 25,
             p: Principal = Depends(require_super_admin), db: DbSession = Depends(get_db)):
    stmt = select(Payment, Order).join(Order, Order.id == Payment.order_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Payment.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"page": page, "size": size, "total": total, "items": [
        {"id": pay.id, "order_id": o.id, "order_number": o.order_number, "method": pay.method,
         "amount_paise": pay.amount_paise, "status": pay.status, "provider_ref": pay.provider_ref,
         "created_at": iso(pay.created_at)} for pay, o in rows]}


@router.get("/refunds")
def refunds(p: Principal = Depends(require_super_admin), db: DbSession = Depends(get_db)):
    rows = db.execute(select(Refund, Order).join(Order, Order.id == Refund.order_id)
                      .order_by(Refund.id.desc()).limit(200)).all()
    return {"items": [{"id": r.id, "order_id": o.id, "order_number": o.order_number,
                       "amount_paise": r.amount_paise, "status": r.status, "reason": r.reason,
                       "created_at": iso(r.created_at), "updated_at": iso(r.updated_at)} for r, o in rows]}


@router.get("/reports/kitchens")
def kitchen_report(days: int = 30, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    since = utcnow() - timedelta(days=min(max(days, 1), 365))
    rows = db.execute(_scoped(
        select(Kitchen.id, Kitchen.name, College.name,
               func.count(Order.id),
               func.sum(func.coalesce(Order.subtotal_paise, 0)))
        .join(College, College.id == Kitchen.college_id)
        .join(Order, (Order.kitchen_id == Kitchen.id) & (Order.status == OrderStatus.COMPLETED)
              & (Order.created_at > since), isouter=True), Kitchen.college_id, p)
        .group_by(Kitchen.id, Kitchen.name, College.name).order_by(func.count(Order.id).desc())).all()
    cancelled = dict(db.execute(select(Order.kitchen_id, func.count()).where(
        Order.created_at > since, Order.status.in_((OrderStatus.CANCELLED, OrderStatus.REJECTED)))
        .group_by(Order.kitchen_id)).all())
    out = []
    for kid, name, college, n, gmv in rows:
        gmv = int(gmv or 0)
        commission = round(gmv * settings.commission_bps / 10000)
        out.append({"kitchen_id": kid, "kitchen": name, "college": college, "completed_orders": n,
                    "cancelled_orders": cancelled.get(kid, 0), "gmv_paise": gmv,
                    "commission_paise": commission, "vendor_payout_paise": gmv - commission})
    return {"days": days, "items": out}


@router.get("/reports/orders.csv")
def export_orders(days: int = 30, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    since = utcnow() - timedelta(days=min(max(days, 1), 365))
    rows = db.scalars(_scoped(select(Order), Order.college_id, p).where(Order.created_at > since)
                      .order_by(Order.id)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order_number", "created_at_utc", "college_id", "kitchen", "status", "payment_method",
                "payment_status", "subtotal_inr", "tax_inr", "total_inr"])
    for o in rows:
        w.writerow([o.order_number, iso(o.created_at), o.college_id, o.kitchen.name, o.status, o.payment_method,
                    o.payment_status, o.subtotal_paise / 100, o.tax_paise / 100, o.total_paise / 100])
    audit(db, p.id, "report.exported", "orders", None, days=days, rows=len(rows))
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=campusbite-orders.csv"})


# ---------------------------------------------------------------- support / audit / flags


@router.get("/support")
def tickets(status: str | None = None, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    stmt = _scoped(select(SupportTicket).join(User, User.id == SupportTicket.user_id), User.college_id, p)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    rows = db.scalars(stmt.order_by(SupportTicket.id.desc()).limit(200)).all()
    out = []
    for t in rows:
        d = ticket_out(t)
        u = db.get(User, t.user_id)
        d["user"] = {"name": u.name, "phone": u.phone}
        d["order_number"] = db.get(Order, t.order_id).order_number if t.order_id else None
        out.append(d)
    return {"items": out}


@router.patch("/support/{tid}")
def update_ticket(tid: int, body: TicketPatch, p: Principal = Depends(require_admin), db: DbSession = Depends(get_db)):
    t = db.get(SupportTicket, tid)
    if not t:
        raise not_found("Ticket")
    owner = db.get(User, t.user_id)
    if admin_college_scope(p) is not None:
        _check_college(p, owner.college_id or -1)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t, k, v)
    t.assigned_to = p.id
    if changes.get("status") == "RESOLVED":
        notify(db, t.user_id, "Support ticket resolved", t.admin_note or "Your issue has been resolved.", t.order_id)
    audit(db, p.id, "support.updated", "support_ticket", t.id, **changes)
    db.commit()
    return ticket_out(t)


@router.get("/audit-logs")
def audit_logs(page: int = 1, size: int = 50, p: Principal = Depends(require_super_admin),
               db: DbSession = Depends(get_db)):
    def ser(a: AuditLog):
        actor = db.get(User, a.actor_id) if a.actor_id else None
        return {"id": a.id, "actor": (actor.name or actor.phone) if actor else "system", "action": a.action,
                "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail, "created_at": iso(a.created_at)}
    return paginate(db, select(AuditLog).order_by(AuditLog.id.desc()), page, size, ser)


@router.get("/flags")
def flags(p: Principal = Depends(require_super_admin), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(FeatureFlag).order_by(FeatureFlag.key)).all()
    return {"items": [{"key": f.key, "enabled": f.enabled, "description": f.description} for f in rows]}


@router.patch("/flags/{key}")
def set_flag(key: str, body: FlagPatch, p: Principal = Depends(require_super_admin), db: DbSession = Depends(get_db)):
    f = db.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
    if not f:
        raise not_found("Flag")
    f.enabled = body.enabled
    audit(db, p.id, "flag.updated", "feature_flag", key, enabled=body.enabled)
    db.commit()
    return {"key": f.key, "enabled": f.enabled}
