"""Request bodies. Responses are plain dicts built in services/common.py."""
from pydantic import BaseModel, Field

PHONE = r"^[6-9]\d{9}$"
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class OtpRequestIn(BaseModel):
    phone: str = Field(pattern=PHONE)


class OtpVerifyIn(BaseModel):
    phone: str = Field(pattern=PHONE)
    code: str = Field(min_length=4, max_length=8)


class RefreshIn(BaseModel):
    refresh_token: str


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    roll_no: str | None = Field(default=None, max_length=50)
    year: str | None = Field(default=None, max_length=30)
    college_id: int | None = None


class CartLine(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=50)
    choice_ids: list[int] = []


class QuoteIn(BaseModel):
    kitchen_id: int
    items: list[CartLine]


class OrderIn(QuoteIn):
    payment_method: str = "MOCK_UPI"
    instructions: str | None = Field(default=None, max_length=300)
    expected_total_paise: int | None = None


class MockPayIn(BaseModel):
    outcome: str = Field(default="success", pattern="^(success|fail)$")


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class VersionedIn(BaseModel):
    version: int


class AcceptIn(VersionedIn):
    eta_minutes: int | None = Field(default=None, ge=1, le=120)


class RejectIn(VersionedIn):
    reason: str = Field(min_length=3, max_length=300)


class StatusIn(VersionedIn):
    status: str = Field(pattern="^(PREPARING|READY)$")


class VerifyPickupIn(BaseModel):
    code: str = Field(min_length=6, max_length=64)  # 6-digit code or full QR payload
    order_id: int | None = None


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


class SupportIn(BaseModel):
    order_id: int | None = None
    category: str = Field(pattern="^(DELAYED|MISSING_ITEM|WRONG_ORDER|PAYMENT|REFUND|OTHER)$")
    message: str = Field(min_length=5, max_length=2000)


# ---------------------------------------------------------------- kitchen


class KitchenRegisterIn(BaseModel):
    college_id: int
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=500)
    cuisine: str = Field(default="", max_length=100)
    counter_location: str = Field(default="", max_length=200)
    fssai_number: str | None = Field(default=None, max_length=30)
    owner_name: str | None = Field(default=None, max_length=120)


class KitchenSettingsIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    counter_location: str | None = Field(default=None, max_length=200)
    emoji: str | None = Field(default=None, max_length=8)
    is_accepting: bool | None = None
    busy_mode: bool | None = None
    prep_minutes: int | None = Field(default=None, ge=1, le=120)
    opens_at: str | None = Field(default=None, pattern=HHMM)
    closes_at: str | None = Field(default=None, pattern=HHMM)


class DayHoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    opens_at: str = Field(pattern=HHMM)
    closes_at: str = Field(pattern=HHMM)
    is_closed: bool = False


class WeeklyHoursIn(BaseModel):
    days: list[DayHoursIn] = Field(min_length=7, max_length=7)


class ClosureIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason: str = Field(default="Holiday", min_length=2, max_length=120)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = 0


class AddonChoiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price_paise: int = Field(default=0, ge=0, le=1_000_000)
    is_available: bool = True


class AddonGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    min_select: int = Field(default=0, ge=0, le=10)
    max_select: int = Field(default=1, ge=1, le=10)
    choices: list[AddonChoiceIn] = Field(min_length=1)


class MenuItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=500)
    price_paise: int = Field(ge=0, le=10_000_000)
    category_id: int | None = None
    is_veg: bool = True
    emoji: str = Field(default="🍲", max_length=8)
    image_url: str | None = Field(default=None, max_length=500)
    is_available: bool = True
    stock_qty: int | None = Field(default=None, ge=0)
    max_per_order: int = Field(default=10, ge=1, le=50)
    is_popular: bool = False
    sku: str | None = Field(default=None, max_length=40)
    addon_groups: list[AddonGroupIn] = []


class MenuItemPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    price_paise: int | None = Field(default=None, ge=0, le=10_000_000)
    category_id: int | None = None
    is_veg: bool | None = None
    emoji: str | None = Field(default=None, max_length=8)
    image_url: str | None = Field(default=None, max_length=500)
    is_available: bool | None = None
    stock_qty: int | None = Field(default=None, ge=0)
    unlimited_stock: bool | None = None
    max_per_order: int | None = Field(default=None, ge=1, le=50)
    is_popular: bool | None = None
    addon_groups: list[AddonGroupIn] | None = None


class StaffIn(BaseModel):
    phone: str = Field(pattern=PHONE)
    name: str | None = Field(default=None, max_length=120)
    role: str = Field(pattern="^(kitchen_manager|kitchen_cashier|kitchen_cook)$")


# ---------------------------------------------------------------- admin


class CollegeIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=20)
    city: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=300)
    lat: float | None = None
    lng: float | None = None
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=15)
    is_active: bool = True


class CollegePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)
    lat: float | None = None
    lng: float | None = None
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=15)
    is_active: bool | None = None


class UserPatch(BaseModel):
    is_active: bool | None = None
    is_flagged: bool | None = None
    college_id: int | None = None
    note: str | None = Field(default=None, max_length=300)


class TicketPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(OPEN|IN_PROGRESS|RESOLVED)$")
    admin_note: str | None = Field(default=None, max_length=2000)


class FlagPatch(BaseModel):
    enabled: bool
