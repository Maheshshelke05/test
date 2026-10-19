"""Database schema. Money is always integer paise; timestamps are naive UTC."""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import ID, Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def pk():
    return mapped_column(ID, primary_key=True, autoincrement=True)


def fk(target: str, nullable=False, ondelete=None):
    return mapped_column(ID, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


class Role:
    STUDENT = "student"
    KITCHEN_OWNER = "kitchen_owner"
    KITCHEN_MANAGER = "kitchen_manager"
    KITCHEN_CASHIER = "kitchen_cashier"
    KITCHEN_COOK = "kitchen_cook"
    COLLEGE_ADMIN = "college_admin"
    SUPER_ADMIN = "super_admin"

    KITCHEN_ROLES = (KITCHEN_OWNER, KITCHEN_MANAGER, KITCHEN_CASHIER, KITCHEN_COOK)


class OrderStatus:
    PENDING_ACCEPTANCE = "PENDING_ACCEPTANCE"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    ACTIVE = (PENDING_ACCEPTANCE, ACCEPTED, PREPARING, READY)
    FINAL = (COMPLETED, REJECTED, CANCELLED)


class PaymentStatus:
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class PaymentMethod:
    MOCK_UPI = "MOCK_UPI"
    MOCK_CARD = "MOCK_CARD"
    CASH = "CASH"

    ONLINE = (MOCK_UPI, MOCK_CARD)
    ALL = (MOCK_UPI, MOCK_CARD, CASH)


class KitchenStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


# ---------------------------------------------------------------- identity


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = pk()
    phone: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200))
    roll_no: Mapped[str | None] = mapped_column(String(50))
    year: Mapped[str | None] = mapped_column(String(30))
    college_id: Mapped[int | None] = fk("colleges.id", nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    college: Mapped["College | None"] = relationship()


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", "kitchen_id", "college_id"),)
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(String(30))
    kitchen_id: Mapped[int | None] = fk("kitchens.id", nullable=True, ondelete="CASCADE")
    college_id: Mapped[int | None] = fk("colleges.id", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="roles")


class OtpRequest(Base):
    __tablename__ = "otp_requests"
    id: Mapped[int] = pk()
    phone: Mapped[str] = mapped_column(String(15), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- campus & vendor


class College(Base):
    __tablename__ = "colleges"
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    city: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(15))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Kitchen(Base):
    __tablename__ = "kitchens"
    id: Mapped[int] = pk()
    college_id: Mapped[int] = fk("colleges.id")
    owner_id: Mapped[int] = fk("users.id")
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(500), default="")
    cuisine: Mapped[str] = mapped_column(String(100), default="")
    counter_location: Mapped[str] = mapped_column(String(200), default="")
    emoji: Mapped[str] = mapped_column(String(8), default="🍽️")
    fssai_number: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default=KitchenStatus.PENDING, index=True)
    status_reason: Mapped[str | None] = mapped_column(String(300))
    is_accepting: Mapped[bool] = mapped_column(Boolean, default=True)
    busy_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=15)
    opens_at: Mapped[str] = mapped_column(String(5), default="08:00")  # local campus time HH:MM
    closes_at: Mapped[str] = mapped_column(String(5), default="21:00")
    rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    college: Mapped[College] = relationship()
    hours: Mapped[list["KitchenHours"]] = relationship(cascade="all, delete-orphan", order_by="KitchenHours.weekday")
    closures: Mapped[list["KitchenClosure"]] = relationship(cascade="all, delete-orphan", order_by="KitchenClosure.date")


class KitchenHours(Base):
    """Weekly schedule in campus local time. Without rows, opens_at/closes_at apply every day."""

    __tablename__ = "kitchen_hours"
    __table_args__ = (UniqueConstraint("kitchen_id", "weekday"),)
    id: Mapped[int] = pk()
    kitchen_id: Mapped[int] = fk("kitchens.id", ondelete="CASCADE")
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday … 6 = Sunday
    opens_at: Mapped[str] = mapped_column(String(5), default="08:00")
    closes_at: Mapped[str] = mapped_column(String(5), default="21:00")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class KitchenClosure(Base):
    """One-off closed day: holiday, exam day, festival, counter maintenance."""

    __tablename__ = "kitchen_closures"
    __table_args__ = (UniqueConstraint("kitchen_id", "date"),)
    id: Mapped[int] = pk()
    kitchen_id: Mapped[int] = fk("kitchens.id", ondelete="CASCADE")
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, campus local date
    reason: Mapped[str] = mapped_column(String(120), default="Closed")


# ---------------------------------------------------------------- catalog


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = pk()
    kitchen_id: Mapped[int] = fk("kitchens.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = pk()
    kitchen_id: Mapped[int] = fk("kitchens.id", ondelete="CASCADE")
    category_id: Mapped[int | None] = fk("categories.id", nullable=True, ondelete="SET NULL")
    sku: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(500), default="")
    price_paise: Mapped[int] = mapped_column(Integer)
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    emoji: Mapped[str] = mapped_column(String(8), default="🍲")
    image_url: Mapped[str | None] = mapped_column(String(500))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_qty: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    max_per_order: Mapped[int] = mapped_column(Integer, default=10)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    addon_groups: Mapped[list["AddonGroup"]] = relationship(
        cascade="all, delete-orphan", order_by="AddonGroup.id"
    )


class AddonGroup(Base):
    """A variant/add-on group, e.g. "Size" (min 1, max 1) or "Extras" (min 0, max 3)."""

    __tablename__ = "addon_groups"
    id: Mapped[int] = pk()
    menu_item_id: Mapped[int] = fk("menu_items.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(80))
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)

    choices: Mapped[list["AddonChoice"]] = relationship(
        cascade="all, delete-orphan", order_by="AddonChoice.id"
    )


class AddonChoice(Base):
    __tablename__ = "addon_choices"
    id: Mapped[int] = pk()
    group_id: Mapped[int] = fk("addon_groups.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(80))
    price_paise: Mapped[int] = mapped_column(Integer, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- commerce


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("student_id", "idempotency_key"),)
    id: Mapped[int] = pk()
    order_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    student_id: Mapped[int] = fk("users.id")
    kitchen_id: Mapped[int] = fk("kitchens.id")
    college_id: Mapped[int] = fk("colleges.id")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.PENDING_ACCEPTANCE, index=True)
    payment_status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.PENDING, index=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0)
    fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(String(300), default="")
    eta_minutes: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(300))  # reject / cancel reason
    version: Mapped[int] = mapped_column(Integer, default=1)
    pickup_nonce: Mapped[str | None] = mapped_column(String(64))
    pickup_hash: Mapped[str | None] = mapped_column(String(64))
    pickup_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    pickup_attempts: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    preparing_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)  # rejected / cancelled
    ack_overdue_flagged: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan", order_by="OrderItem.id")
    kitchen: Mapped[Kitchen] = relationship()
    student: Mapped[User] = relationship()


class OrderItem(Base):
    """Immutable snapshot of what was bought, independent of later menu edits."""

    __tablename__ = "order_items"
    id: Mapped[int] = pk()
    order_id: Mapped[int] = fk("orders.id", ondelete="CASCADE")
    menu_item_id: Mapped[int] = fk("menu_items.id")
    name: Mapped[str] = mapped_column(String(150))
    is_veg: Mapped[bool] = mapped_column(Boolean, default=True)
    unit_price_paise: Mapped[int] = mapped_column(Integer)  # base + selected options
    quantity: Mapped[int] = mapped_column(Integer)
    options: Mapped[list] = mapped_column(JSON, default=list)  # [{group, name, price_paise}]
    line_total_paise: Mapped[int] = mapped_column(Integer)


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[int] = pk()
    order_id: Mapped[int] = fk("orders.id", ondelete="CASCADE")
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[int | None] = fk("users.id", nullable=True)
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- payments


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = pk()
    order_id: Mapped[int] = fk("orders.id")
    method: Mapped[str] = mapped_column(String(20))
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.PENDING)
    provider_ref: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"
    id: Mapped[int] = pk()
    event_id: Mapped[str] = mapped_column(String(80), unique=True)
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = pk()
    payment_id: Mapped[int] = fk("payments.id")
    order_id: Mapped[int] = fk("orders.id")
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="INITIATED")  # INITIATED/SUCCEEDED/FAILED
    reason: Mapped[str] = mapped_column(String(300))
    actor_id: Mapped[int | None] = fk("users.id", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- experience


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "menu_item_id"),)
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    menu_item_id: Mapped[int] = fk("menu_items.id", ondelete="CASCADE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    order_id: Mapped[int | None] = fk("orders.id", nullable=True)
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(String(400))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = pk()
    user_id: Mapped[int] = fk("users.id")
    order_id: Mapped[int | None] = fk("orders.id", nullable=True)
    category: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN/IN_PROGRESS/RESOLVED
    admin_note: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[int | None] = fk("users.id", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- governance


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = pk()
    actor_id: Mapped[int | None] = fk("users.id", nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    id: Mapped[int] = pk()
    key: Mapped[str] = mapped_column(String(60), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(200), default="")
