"""Student-facing discovery, profile, cart quote, orders, pickup and support."""
import difflib
import math

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..deps import Principal, admin_college_scope, get_principal
from ..errors import ApiError, not_found
from ..models import (
    Category,
    College,
    Favorite,
    Kitchen,
    KitchenStatus,
    MenuItem,
    Notification,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    SupportTicket,
)
from ..schemas import CartLine, MockPayIn, OrderIn, ProfileIn, QuoteIn, RatingIn, SupportIn
from ..services import ordering, payments
from ..services.common import (
    audit,
    college_out,
    flag_enabled,
    item_out,
    iso,
    kitchen_out,
    order_out,
    paginate,
)

router = APIRouter(prefix="/v1", tags=["student"])


def _km(lat1, lng1, lat2, lng2) -> float:
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2)
    return 12742 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- discovery (public)


@router.get("/colleges")
def list_colleges(q: str = "", lat: float | None = None, lng: float | None = None,
                  db: DbSession = Depends(get_db)):
    stmt = select(College).where(College.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(College.name.ilike(like), College.city.ilike(like), College.code.ilike(like)))
    colleges = db.scalars(stmt.order_by(College.name)).all()
    rows = []
    for c in colleges:
        d = _km(lat, lng, c.lat, c.lng) if None not in (lat, lng, c.lat, c.lng) else None
        rows.append(college_out(c, d))
    if lat is not None:
        rows.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0))
    return {"items": rows}


def _approved_kitchen(db, kitchen_id: int) -> Kitchen:
    k = db.get(Kitchen, kitchen_id)
    if not k or k.status != KitchenStatus.APPROVED:
        raise not_found("Kitchen")
    return k


@router.get("/colleges/{college_id}/kitchens")
def college_kitchens(college_id: int, q: str = "", veg_only: bool = False, db: DbSession = Depends(get_db)):
    stmt = select(Kitchen).where(Kitchen.college_id == college_id, Kitchen.status == KitchenStatus.APPROVED)
    if q:
        stmt = stmt.where(or_(Kitchen.name.ilike(f"%{q}%"), Kitchen.cuisine.ilike(f"%{q}%")))
    kitchens = db.scalars(stmt.order_by(Kitchen.name)).all()
    out = []
    for k in kitchens:
        if veg_only:
            has_veg = db.scalar(select(MenuItem.id).where(MenuItem.kitchen_id == k.id, MenuItem.is_veg.is_(True),
                                                          MenuItem.is_deleted.is_(False)).limit(1))
            if not has_veg:
                continue
        out.append(kitchen_out(k))
    out.sort(key=lambda k: (not k["is_open"], k["prep_minutes"]))
    return {"items": out}


@router.get("/kitchens/{kitchen_id}")
def kitchen_detail(kitchen_id: int, db: DbSession = Depends(get_db)):
    return kitchen_out(_approved_kitchen(db, kitchen_id))


@router.get("/kitchens/{kitchen_id}/menu")
def kitchen_menu(kitchen_id: int, db: DbSession = Depends(get_db)):
    k = _approved_kitchen(db, kitchen_id)
    cats = db.scalars(select(Category).where(Category.kitchen_id == k.id)
                      .order_by(Category.sort_order, Category.id)).all()
    items = db.scalars(select(MenuItem).where(MenuItem.kitchen_id == k.id, MenuItem.is_deleted.is_(False))
                       .order_by(MenuItem.id)).all()
    return {
        "kitchen": kitchen_out(k),
        "categories": [{"id": c.id, "name": c.name} for c in cats],
        "items": [item_out(i) for i in items],
    }


def _college_items(db, college_id: int):
    return (select(MenuItem, Kitchen)
            .join(Kitchen, Kitchen.id == MenuItem.kitchen_id)
            .where(Kitchen.college_id == college_id, Kitchen.status == KitchenStatus.APPROVED,
                   MenuItem.is_deleted.is_(False)))


def _group_by_kitchen(rows) -> list:
    groups: dict[int, dict] = {}
    for item, kitchen in rows:
        g = groups.setdefault(kitchen.id, {"kitchen": kitchen_out(kitchen), "items": []})
        g["items"].append(item_out(item))
    return list(groups.values())


def _search(db, college_id: int, terms: list[str]):
    stmt = _college_items(db, college_id)
    for t in terms:
        stmt = stmt.where(or_(MenuItem.name.ilike(f"%{t}%"), MenuItem.description.ilike(f"%{t}%")))
    return db.execute(stmt.limit(60)).all()


@router.get("/colleges/{college_id}/search")
def search_food(college_id: int, q: str, db: DbSession = Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return {"query": q, "results": [], "suggestion": None}
    terms = q.lower().split()
    rows = _search(db, college_id, terms)
    suggestion = None
    if not rows:
        # Spelling tolerance: correct each word against dish-name words in this college
        # ("magi" -> "maggi"), then search again; last resort, closest whole dish names.
        names = [i.name for i, _ in db.execute(_college_items(db, college_id)).all()]
        vocab = sorted({w.lower() for n in names for w in n.split() if len(w) > 2})
        fixed = [(difflib.get_close_matches(t, vocab, n=1, cutoff=0.6) or [t])[0] for t in terms]
        if fixed != terms:
            suggestion = " ".join(fixed)
            rows = _search(db, college_id, fixed)
        if not rows:
            close = difflib.get_close_matches(q.lower(), [n.lower() for n in names], n=8, cutoff=0.55)
            if close:
                suggestion = close[0]
                rows = db.execute(_college_items(db, college_id)
                                  .where(func.lower(MenuItem.name).in_(close))).all()
    return {"query": q, "results": _group_by_kitchen(rows), "suggestion": suggestion}


@router.get("/colleges/{college_id}/popular")
def popular(college_id: int, db: DbSession = Depends(get_db)):
    rows = db.execute(_college_items(db, college_id).where(MenuItem.is_popular.is_(True)).limit(20)).all()
    out = []
    for item, kitchen in rows:
        d = item_out(item)
        d["kitchen"] = {"id": kitchen.id, "name": kitchen.name}
        out.append(d)
    return {"items": out}


# ---------------------------------------------------------------- profile


@router.patch("/me")
def update_profile(body: ProfileIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    user = db.merge(p.user)
    data = body.model_dump(exclude_unset=True)
    if "college_id" in data and data["college_id"] is not None:
        college = db.get(College, data["college_id"])
        if not college or not college.is_active:
            raise ApiError(400, "INVALID_COLLEGE", "Please choose an active college")
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    from .auth import _me
    return _me(db, user)


@router.get("/me/favorites")
def favorites(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    rows = db.execute(select(MenuItem, Kitchen).join(Favorite, Favorite.menu_item_id == MenuItem.id)
                      .join(Kitchen, Kitchen.id == MenuItem.kitchen_id)
                      .where(Favorite.user_id == p.id, MenuItem.is_deleted.is_(False),
                             Kitchen.status == KitchenStatus.APPROVED)).all()
    out = []
    for item, kitchen in rows:
        d = item_out(item)
        d["kitchen"] = {"id": kitchen.id, "name": kitchen.name, "college_id": kitchen.college_id}
        out.append(d)
    return {"items": out}


@router.post("/me/favorites/{item_id}")
def add_favorite(item_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    if not db.get(MenuItem, item_id):
        raise not_found("Item")
    if not db.scalar(select(Favorite).where(Favorite.user_id == p.id, Favorite.menu_item_id == item_id)):
        db.add(Favorite(user_id=p.id, menu_item_id=item_id))
        db.commit()
    return {"ok": True}


@router.delete("/me/favorites/{item_id}")
def remove_favorite(item_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    fav = db.scalar(select(Favorite).where(Favorite.user_id == p.id, Favorite.menu_item_id == item_id))
    if fav:
        db.delete(fav)
        db.commit()
    return {"ok": True}


@router.get("/me/notifications")
def notifications(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == p.id)
                      .order_by(Notification.id.desc()).limit(50)).all()
    return {"items": [{"id": n.id, "title": n.title, "body": n.body, "order_id": n.order_id,
                       "is_read": n.is_read, "created_at": iso(n.created_at)} for n in rows],
            "unread": sum(1 for n in rows if not n.is_read)}


@router.post("/me/notifications/read")
def mark_read(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == p.id).values(is_read=True))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- orders


def load_order(db, p: Principal, order_id: int) -> Order:
    """Student owner, kitchen staff of that kitchen, or an admin in scope."""
    order = db.get(Order, order_id)
    if not order:
        raise not_found("Order")
    if order.student_id == p.id or p.kitchen_role(order.kitchen_id):
        return order
    scope = admin_college_scope(p) if (p.is_super_admin or p.college_admin_ids()) else set()
    if scope is None or order.college_id in scope:
        return order
    raise not_found("Order")


def _own_order(db, p: Principal, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order or order.student_id != p.id:
        raise not_found("Order")
    return order


@router.post("/orders/quote")
def quote(body: QuoteIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    return ordering.build_quote(db, p.user, body.kitchen_id, body.items, strict=False)


@router.post("/orders", status_code=201)
def place_order(body: OrderIn, idempotency_key: str = Header(min_length=8, max_length=80),
                p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    order = ordering.create_order(db, p.user, body, idempotency_key)
    return order_out(order)


@router.get("/orders")
def my_orders(page: int = 1, size: int = 20, active: bool | None = None,
              p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    stmt = select(Order).where(Order.student_id == p.id)
    if active is True:
        stmt = stmt.where(Order.status.in_(OrderStatus.ACTIVE))
    elif active is False:
        stmt = stmt.where(Order.status.in_(OrderStatus.FINAL))
    return paginate(db, stmt.order_by(Order.id.desc()), page, size, order_out)


@router.get("/orders/{order_id}")
def get_order(order_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    order = load_order(db, p, order_id)
    return order_out(order, include_student=order.student_id != p.id)


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    order = _own_order(db, p, order_id)
    if order.status != OrderStatus.PENDING_ACCEPTANCE:
        raise ApiError(409, "CANNOT_CANCEL", "Order can only be cancelled before the kitchen accepts it")
    return order_out(ordering.transition(db, order, OrderStatus.CANCELLED, p.id, None,
                                         note="Cancelled by student"))


@router.post("/orders/{order_id}/pay")
def mock_pay(order_id: int, body: MockPayIn, p: Principal = Depends(get_principal),
             db: DbSession = Depends(get_db)):
    """Local sandbox stand-in for a gateway checkout. Produces a signed gateway event."""
    order = _own_order(db, p, order_id)
    if order.payment_method not in PaymentMethod.ONLINE:
        raise ApiError(400, "NOT_ONLINE", "This order is pay-at-counter")
    if order.status != OrderStatus.PENDING_ACCEPTANCE:
        raise ApiError(409, "ORDER_CLOSED", "This order can no longer be paid")
    if order.payment_status == PaymentStatus.FAILED:
        payments.retry_payment(db, order)
    elif order.payment_status != PaymentStatus.PENDING:
        raise ApiError(409, "ALREADY_PAID", "This order is already paid")
    result = payments.process_event(db, payments.mock_gateway_event(order, body.outcome))
    db.refresh(order)
    return {"result": result, "order": order_out(order)}


@router.get("/orders/{order_id}/pickup-code")
def pickup_code(order_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    return ordering.get_or_rotate_pickup(db, _own_order(db, p, order_id))


@router.post("/orders/{order_id}/rate")
def rate(order_id: int, body: RatingIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    order = _own_order(db, p, order_id)
    if order.status != OrderStatus.COMPLETED:
        raise ApiError(409, "NOT_COMPLETED", "You can rate only completed orders")
    if order.rating:
        raise ApiError(409, "ALREADY_RATED", "You already rated this order")
    if not flag_enabled(db, "ratings"):
        raise ApiError(400, "RATINGS_DISABLED", "Ratings are turned off")
    order.rating = body.rating
    db.execute(update(Kitchen).where(Kitchen.id == order.kitchen_id)
               .values(rating_sum=Kitchen.rating_sum + body.rating, rating_count=Kitchen.rating_count + 1))
    db.commit()
    return {"ok": True}


@router.post("/orders/{order_id}/reorder")
def reorder(order_id: int, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    """Re-quote a past order at today's prices; unavailable lines are reported, not silently dropped."""
    order = _own_order(db, p, order_id)
    lines = [CartLine(menu_item_id=it.menu_item_id, quantity=it.quantity,
                      choice_ids=[o["choice_id"] for o in it.options if "choice_id" in o])
             for it in order.items]
    return ordering.build_quote(db, p.user, order.kitchen_id, lines, strict=False)


# ---------------------------------------------------------------- support


def ticket_out(t: SupportTicket) -> dict:
    return {"id": t.id, "user_id": t.user_id, "order_id": t.order_id, "category": t.category,
            "message": t.message, "status": t.status, "admin_note": t.admin_note,
            "created_at": iso(t.created_at), "updated_at": iso(t.updated_at)}


@router.post("/support", status_code=201)
def create_ticket(body: SupportIn, p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    if body.order_id is not None:
        _own_order(db, p, body.order_id)
    t = SupportTicket(user_id=p.id, order_id=body.order_id, category=body.category, message=body.message)
    db.add(t)
    db.flush()
    audit(db, p.id, "support.created", "support_ticket", t.id)
    db.commit()
    return ticket_out(t)


@router.get("/support")
def my_tickets(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(SupportTicket).where(SupportTicket.user_id == p.id)
                      .order_by(SupportTicket.id.desc())).all()
    return {"items": [ticket_out(t) for t in rows]}
