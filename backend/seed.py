"""Deterministic demo data. Usage:  python seed.py   (drops and recreates all tables)

Accounts (OTP is 123456 in local mode):
  Super admin       9000000000
  College admin     9000000001  (North Campus only)
  Kitchen owners    9100000001 … 9100000009   (kitchen 1 … 9)
  Kitchen cashiers  9200000001 … 9200000009
  Kitchen cooks     9300000001 … 9300000009
  Pending owner     9100000010  (kitchen awaiting approval)
  Students          9800000001 … 9800000030  (9800000001 = Aarav, North Campus)
"""
import random
from datetime import timedelta

from sqlalchemy import func, select, text

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.migrate import upgrade_db
from app.models import (
    AddonChoice,
    AddonGroup,
    Category,
    College,
    FeatureFlag,
    Kitchen,
    KitchenStatus,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    Payment,
    PaymentStatus,
    Role,
    User,
    UserRole,
    utcnow,
)

R = random.Random(42)

COLLEGES = [
    ("North Campus Institute of Technology", "NCIT", "Pune", "Shivajinagar, Pune 411005", 18.5308, 73.8475),
    ("Riverside College of Commerce", "RCC", "Solapur", "Railway Lines, Solapur 413001", 17.6599, 75.9064),
    ("Hilltop Science College", "HSC", "Pune", "Kothrud, Pune 411038", 18.5074, 73.8077),
]

# (name, cuisine, emoji, counter, prep, menu: {category: [(name, price_inr, veg, emoji, popular)]})
KITCHENS = [
    ("Campus Canteen", "Snacks • Maggi • Chai", "🍜", "Ground floor, Block A", 12, {
        "Maggi & Noodles": [("Cheese Maggi", 60, True, "🍜", True), ("Masala Maggi", 45, True, "🍜", False),
                            ("Egg Maggi", 65, False, "🍳", False), ("Veg Hakka Noodles", 80, True, "🍝", False),
                            ("Schezwan Noodles", 90, True, "🌶️", False)],
        "Snacks": [("Vada Pav", 20, True, "🍔", True), ("Samosa (2 pcs)", 30, True, "🥟", False),
                   ("Poha", 35, True, "🍛", False), ("Misal Pav", 70, True, "🍲", True),
                   ("Bread Omelette", 50, False, "🍳", False)],
        "Sandwiches": [("Veg Grilled Sandwich", 70, True, "🥪", False), ("Cheese Corn Sandwich", 85, True, "🥪", False),
                       ("Bombay Masala Toast", 60, True, "🥪", False), ("Chicken Sandwich", 110, False, "🥪", False),
                       ("Paneer Tikka Sandwich", 100, True, "🥪", False)],
        "Beverages": [("Cutting Chai", 15, True, "☕", True), ("Filter Coffee", 25, True, "☕", False),
                      ("Cold Coffee", 60, True, "🧋", False), ("Lemon Soda", 30, True, "🍋", False),
                      ("Masala Chaas", 25, True, "🥛", False)],
    }),
    ("Chai Point Corner", "Tea • Coffee • Bakes", "☕", "Library lawn kiosk", 8, {
        "Tea": [("Adrak Chai", 20, True, "☕", True), ("Elaichi Chai", 20, True, "☕", False),
                ("Green Tea", 30, True, "🍵", False), ("Lemon Tea", 25, True, "🍋", False),
                ("Kashmiri Kahwa", 45, True, "🍵", False)],
        "Coffee": [("Hot Coffee", 35, True, "☕", False), ("Cappuccino", 70, True, "☕", True),
                   ("Cold Brew", 90, True, "🧋", False), ("Hazelnut Frappe", 120, True, "🥤", False),
                   ("Mocha", 95, True, "☕", False)],
        "Bakes": [("Butter Croissant", 60, True, "🥐", False), ("Choco Muffin", 55, True, "🧁", True),
                  ("Banana Bread", 50, True, "🍞", False), ("Jeera Cookies (4)", 30, True, "🍪", False),
                  ("Veg Puff", 30, True, "🥟", False)],
        "Quick Bites": [("Bun Maska", 30, True, "🍞", True), ("Khari Biscuit", 20, True, "🥨", False),
                        ("Egg Puff", 40, False, "🥚", False), ("Cheese Toast", 50, True, "🍞", False),
                        ("Peri Peri Fries", 70, True, "🍟", False)],
    }),
    ("Punjabi Dhaba", "North Indian • Thali", "🍛", "Food court, counter 3", 18, {
        "Thalis": [("Veg Thali", 120, True, "🍱", True), ("Paneer Thali", 150, True, "🍱", False),
                   ("Chicken Thali", 180, False, "🍗", True), ("Mini Thali", 90, True, "🍱", False),
                   ("Rajma Chawal", 100, True, "🍛", False)],
        "Main Course": [("Paneer Butter Masala", 140, True, "🧈", False), ("Dal Makhani", 110, True, "🍲", False),
                        ("Chole", 90, True, "🍲", False), ("Butter Chicken", 170, False, "🍗", False),
                        ("Mix Veg", 100, True, "🥘", False)],
        "Breads": [("Butter Roti", 15, True, "🫓", False), ("Butter Naan", 30, True, "🫓", False),
                   ("Aloo Paratha", 60, True, "🫓", True), ("Paneer Paratha", 80, True, "🫓", False),
                   ("Laccha Paratha", 40, True, "🫓", False)],
        "Rice": [("Jeera Rice", 70, True, "🍚", False), ("Veg Pulao", 90, True, "🍚", False),
                 ("Chicken Biryani", 160, False, "🍗", True), ("Veg Biryani", 130, True, "🍚", False),
                 ("Curd Rice", 70, True, "🍚", False)],
    }),
    ("Wrap & Roll", "Rolls • Frankies", "🌯", "Near main gate", 10, {
        "Veg Rolls": [("Paneer Tikka Roll", 90, True, "🌯", True), ("Aloo Tikki Roll", 60, True, "🌯", False),
                      ("Mushroom Roll", 85, True, "🌯", False), ("Cheese Corn Roll", 80, True, "🌯", False),
                      ("Veg Frankie", 55, True, "🌯", False)],
        "Non-Veg Rolls": [("Chicken Tikka Roll", 110, False, "🌯", True), ("Egg Roll", 60, False, "🌯", False),
                          ("Double Egg Chicken Roll", 130, False, "🌯", False), ("Mutton Seekh Roll", 150, False, "🌯", False),
                          ("Chicken Frankie", 95, False, "🌯", False)],
        "Sides": [("Salted Fries", 60, True, "🍟", False), ("Cheese Fries", 90, True, "🍟", False),
                  ("Onion Rings", 70, True, "🧅", False), ("Chicken Nuggets", 110, False, "🍗", False),
                  ("Corn Cup", 50, True, "🌽", False)],
        "Drinks": [("Coke", 40, True, "🥤", False), ("Lassi", 50, True, "🥛", False),
                   ("Iced Tea", 55, True, "🧊", False), ("Mint Mojito", 70, True, "🍹", False),
                   ("Water Bottle", 20, True, "💧", False)],
    }),
    ("Juice Junction", "Juices • Shakes", "🥤", "Sports complex", 6, {
        "Fresh Juices": [("Orange Juice", 60, True, "🍊", True), ("Watermelon Juice", 50, True, "🍉", False),
                         ("Mosambi Juice", 55, True, "🍋", False), ("Pineapple Juice", 60, True, "🍍", False),
                         ("ABC Juice", 80, True, "🥕", False)],
        "Shakes": [("Banana Shake", 60, True, "🍌", False), ("Chikoo Shake", 70, True, "🥤", False),
                   ("Oreo Shake", 90, True, "🥤", True), ("Mango Shake", 80, True, "🥭", False),
                   ("Cold Coffee Shake", 80, True, "🧋", False)],
        "Smoothies": [("Berry Smoothie", 110, True, "🫐", False), ("Banana Oats Smoothie", 100, True, "🥣", False),
                      ("Green Detox", 100, True, "🥬", False), ("Mango Yogurt", 100, True, "🥭", False),
                      ("Peanut Butter Smoothie", 120, True, "🥜", False)],
        "Light Bites": [("Fruit Bowl", 70, True, "🍓", True), ("Sprouts Chaat", 50, True, "🥗", False),
                        ("Corn Chaat", 50, True, "🌽", False), ("Granola Bar", 40, True, "🍫", False),
                        ("Boiled Eggs (2)", 30, False, "🥚", False)],
    }),
    ("Pizza Hub", "Pizza • Pasta", "🍕", "Food court, counter 1", 15, {
        "Pizzas": [("Margherita Pizza", 120, True, "🍕", True), ("Farmhouse Pizza", 170, True, "🍕", False),
                   ("Paneer Tikka Pizza", 180, True, "🍕", False), ("Chicken BBQ Pizza", 200, False, "🍕", True),
                   ("Corn Cheese Pizza", 140, True, "🍕", False)],
        "Pasta": [("White Sauce Pasta", 130, True, "🍝", False), ("Red Sauce Pasta", 120, True, "🍝", False),
                  ("Pink Sauce Pasta", 140, True, "🍝", False), ("Chicken Alfredo", 170, False, "🍝", False),
                  ("Mac & Cheese", 130, True, "🧀", False)],
        "Garlic Bread": [("Garlic Bread", 80, True, "🥖", False), ("Cheese Garlic Bread", 100, True, "🥖", True),
                         ("Stuffed Garlic Bread", 130, True, "🥖", False), ("Chilli Cheese Toast", 90, True, "🌶️", False),
                         ("Bruschetta", 110, True, "🍅", False)],
        "Desserts": [("Choco Lava Cake", 90, True, "🍫", False), ("Brownie", 70, True, "🍫", False),
                     ("Tiramisu Cup", 120, True, "🍰", False), ("Ice Cream Scoop", 50, True, "🍨", False),
                     ("Cold Coffee", 70, True, "🧋", False)],
    }),
    ("Momos Express", "Momos • Chinese", "🥟", "Hostel road", 10, {
        "Steamed Momos": [("Veg Steamed Momos", 70, True, "🥟", True), ("Paneer Momos", 90, True, "🥟", False),
                          ("Chicken Momos", 100, False, "🥟", True), ("Corn Cheese Momos", 90, True, "🥟", False),
                          ("Mushroom Momos", 85, True, "🥟", False)],
        "Fried & Tandoori": [("Veg Fried Momos", 80, True, "🥟", False), ("Chicken Fried Momos", 110, False, "🥟", False),
                             ("Tandoori Veg Momos", 110, True, "🔥", False), ("Tandoori Chicken Momos", 140, False, "🔥", False),
                             ("Kurkure Momos", 100, True, "🥟", False)],
        "Chinese": [("Veg Manchurian", 90, True, "🥢", False), ("Chilli Paneer", 130, True, "🌶️", False),
                    ("Chilli Chicken", 150, False, "🌶️", False), ("Veg Fried Rice", 100, True, "🍚", False),
                    ("Spring Rolls", 80, True, "🥢", False)],
        "Soups": [("Manchow Soup", 60, True, "🍜", False), ("Hot & Sour Soup", 60, True, "🍜", False),
                  ("Sweet Corn Soup", 55, True, "🌽", False), ("Chicken Clear Soup", 80, False, "🍜", False),
                  ("Thukpa", 110, True, "🍜", False)],
    }),
    ("Desi Thali House", "Maharashtrian • Thali", "🥘", "Hostel mess annex", 16, {
        "Thali": [("Maharashtrian Thali", 110, True, "🍱", True), ("Puran Poli Thali", 130, True, "🍱", False),
                  ("Jowar Bhakri Thali", 100, True, "🍱", False), ("Kolhapuri Chicken Thali", 170, False, "🍗", False),
                  ("Fish Thali", 190, False, "🐟", False)],
        "Specials": [("Pav Bhaji", 80, True, "🍛", True), ("Sabudana Khichdi", 50, True, "🍚", False),
                     ("Thalipeeth", 60, True, "🫓", False), ("Usal Pav", 60, True, "🍲", False),
                     ("Zunka Bhakar", 70, True, "🫓", False)],
        "Rice": [("Masale Bhaat", 80, True, "🍚", False), ("Dal Khichdi", 70, True, "🍚", False),
                 ("Varan Bhaat", 60, True, "🍚", False), ("Egg Curry Rice", 90, False, "🥚", False),
                 ("Tomato Rice", 60, True, "🍅", False)],
        "Sweets": [("Shrikhand", 40, True, "🍮", False), ("Gulab Jamun (2)", 30, True, "🍡", False),
                   ("Modak", 25, True, "🥟", False), ("Basundi", 50, True, "🥛", False),
                   ("Kharvas", 40, True, "🍮", False)],
    }),
    ("Sweet Tooth Bakery", "Cakes • Desserts", "🧁", "Admin block cafe", 8, {
        "Cakes": [("Chocolate Truffle Slice", 80, True, "🍰", True), ("Red Velvet Slice", 90, True, "🍰", False),
                  ("Black Forest Slice", 75, True, "🍰", False), ("Pineapple Pastry", 60, True, "🍰", False),
                  ("Blueberry Cheesecake", 140, True, "🍰", False)],
        "Cookies & Brownies": [("Walnut Brownie", 70, True, "🍫", True), ("Choco Chip Cookie", 40, True, "🍪", False),
                               ("Oatmeal Cookie", 40, True, "🍪", False), ("Fudge Brownie", 80, True, "🍫", False),
                               ("Nutella Brownie", 100, True, "🍫", False)],
        "Ice Cream": [("Vanilla Cup", 40, True, "🍨", False), ("Sundae", 110, True, "🍨", False),
                      ("Kulfi", 40, True, "🍡", False), ("Brownie Sundae", 140, True, "🍨", False),
                      ("Mango Sorbet", 70, True, "🥭", False)],
        "Savory": [("Veg Patty", 30, True, "🥟", False), ("Paneer Puff", 40, True, "🥟", False),
                   ("Chicken Puff", 50, False, "🥟", False), ("Pizza Bun", 45, True, "🍕", False),
                   ("Garlic Stick", 35, True, "🥖", False)],
    }),
]

STUDENT_NAMES = ["Aarav", "Diya", "Vihaan", "Ananya", "Arjun", "Isha", "Kabir", "Meera", "Rohan", "Sanya",
                 "Aditya", "Neha", "Siddharth", "Pooja", "Omkar", "Sakshi", "Yash", "Tanvi", "Pranav", "Riya",
                 "Atharva", "Gauri", "Harsh", "Kavya", "Nikhil", "Shruti", "Varun", "Aditi", "Tejas", "Mrunal"]


def addons_for(name: str) -> list[AddonGroup]:
    if "Pizza" in name:
        return [AddonGroup(name="Size", min_select=1, max_select=1, choices=[
                    AddonChoice(name="Regular", price_paise=0), AddonChoice(name="Medium", price_paise=6000),
                    AddonChoice(name="Large", price_paise=12000)]),
                AddonGroup(name="Extra toppings", min_select=0, max_select=3, choices=[
                    AddonChoice(name="Extra cheese", price_paise=3000), AddonChoice(name="Jalapeños", price_paise=2000),
                    AddonChoice(name="Olives", price_paise=2000)])]
    if "Maggi" in name or "Momos" in name:
        return [AddonGroup(name="Add-ons", min_select=0, max_select=2, choices=[
                    AddonChoice(name="Extra cheese", price_paise=1500), AddonChoice(name="Extra spicy", price_paise=0)])]
    if any(w in name for w in ("Shake", "Coffee", "Cappuccino", "Frappe")):
        return [AddonGroup(name="Size", min_select=1, max_select=1, choices=[
                    AddonChoice(name="Regular", price_paise=0), AddonChoice(name="Large", price_paise=2000)])]
    return []


def main(if_empty: bool = False, wipe_confirmed: bool = False):
    if if_empty:
        upgrade_db()
        with SessionLocal() as check:
            if check.scalar(select(func.count(College.id))):
                print("Database already has data; seed skipped.")
                return
    else:
        if not settings.is_local and not wipe_confirmed:
            raise SystemExit("Refusing to wipe a non-local database. Use --if-empty, or --yes-wipe-everything.")
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        upgrade_db()  # schema comes from migrations, same as production
    db = SessionLocal()

    colleges = [College(name=n, code=c, city=city, address=a, lat=lat, lng=lng,
                        contact_name="Campus Office", contact_phone="9000000099")
                for n, c, city, a, lat, lng in COLLEGES]
    db.add_all(colleges)
    db.flush()

    admin = User(phone="9000000000", name="Platform Admin", roles=[UserRole(role=Role.SUPER_ADMIN)])
    cadmin = User(phone="9000000001", name="NCIT Campus Admin", college_id=colleges[0].id,
                  roles=[UserRole(role=Role.COLLEGE_ADMIN, college_id=colleges[0].id)])
    db.add_all([admin, cadmin])
    db.flush()

    kitchens, items_by_kitchen = [], {}
    for i, (name, cuisine, emoji, counter, prep, menu) in enumerate(KITCHENS, start=1):
        college = colleges[(i - 1) // 3]
        owner = User(phone=f"91000000{i:02d}", name=f"{name} Owner")
        cashier = User(phone=f"92000000{i:02d}", name=f"{name} Cashier")
        cook = User(phone=f"93000000{i:02d}", name=f"{name} Cook")
        db.add_all([owner, cashier, cook])
        db.flush()
        k = Kitchen(college_id=college.id, owner_id=owner.id, name=name, cuisine=cuisine, emoji=emoji,
                    description=f"{cuisine} — freshly made at {college.code}.", counter_location=counter,
                    prep_minutes=prep, status=KitchenStatus.APPROVED, opens_at="00:00", closes_at="23:59",
                    fssai_number=f"1152{i:010d}")
        if i == 8:
            k.is_accepting = False  # demo: a closed kitchen stays discoverable but not orderable
        db.add(k)
        db.flush()
        db.add_all([UserRole(user_id=owner.id, role=Role.KITCHEN_OWNER, kitchen_id=k.id),
                    UserRole(user_id=cashier.id, role=Role.KITCHEN_CASHIER, kitchen_id=k.id),
                    UserRole(user_id=cook.id, role=Role.KITCHEN_COOK, kitchen_id=k.id)])
        items = []
        for sort, (cat_name, dishes) in enumerate(menu.items()):
            cat = Category(kitchen_id=k.id, name=cat_name, sort_order=sort)
            db.add(cat)
            db.flush()
            for j, (dish, price, veg, em, popular) in enumerate(dishes):
                item = MenuItem(kitchen_id=k.id, category_id=cat.id, name=dish, price_paise=price * 100,
                                is_veg=veg, emoji=em, is_popular=popular, sku=f"K{i}-{sort}{j}",
                                description=f"{'Veg' if veg else 'Non-veg'} • {cat_name.lower()}",
                                addon_groups=addons_for(dish))
                if dish == "Cheese Maggi":
                    item.stock_qty = 20  # matches the pilot walkthrough
                if dish == "Blueberry Cheesecake":
                    item.stock_qty = 0
                items.append(item)
        db.add_all(items)
        db.flush()
        kitchens.append(k)
        items_by_kitchen[k.id] = items

    pending_owner = User(phone="9100000010", name="New Vendor")
    db.add(pending_owner)
    db.flush()
    pk = Kitchen(college_id=colleges[0].id, owner_id=pending_owner.id, name="Biryani Bros",
                 cuisine="Biryani", emoji="🍗", counter_location="Food court, counter 5",
                 status=KitchenStatus.PENDING, fssai_number="11520000000099")
    db.add(pk)
    db.flush()
    db.add(UserRole(user_id=pending_owner.id, role=Role.KITCHEN_OWNER, kitchen_id=pk.id))

    students = []
    for n in range(1, 31):
        college = colleges[(n - 1) % 3] if n > 1 else colleges[0]
        s = User(phone=f"98000000{n:02d}", name=STUDENT_NAMES[n - 1], college_id=college.id,
                 roll_no=f"{college.code}{2023000 + n}", year=R.choice(["FY", "SY", "TY", "BE"]),
                 email=f"{STUDENT_NAMES[n - 1].lower()}@{college.code.lower()}.edu.in",
                 roles=[UserRole(role=Role.STUDENT)])
        students.append(s)
    db.add_all(students)
    db.flush()

    # 200 historical orders over the last 14 days for reports and dashboards.
    now = utcnow()
    for n in range(200):
        s = R.choice(students)
        k = R.choice([k for k in kitchens if k.college_id == s.college_id])
        created = now - timedelta(days=R.randint(0, 13), hours=R.randint(0, 10), minutes=R.randint(0, 59))
        lines = R.sample([it for it in items_by_kitchen[k.id] if not it.addon_groups], k=R.randint(1, 3))
        status = R.choices([OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED],
                           weights=[88, 7, 5])[0]
        method = R.choice(["MOCK_UPI", "MOCK_UPI", "MOCK_CARD", "CASH"])
        o = Order(student_id=s.id, kitchen_id=k.id, college_id=k.college_id, idempotency_key=f"seed-{n}",
                  payment_method=method, created_at=created, eta_minutes=k.prep_minutes, status=status,
                  subtotal_paise=0, total_paise=0, version=5)
        sub = 0
        for it in lines:
            q = R.randint(1, 2)
            o.items.append(OrderItem(menu_item_id=it.id, name=it.name, is_veg=it.is_veg,
                                     unit_price_paise=it.price_paise, quantity=q,
                                     options=[], line_total_paise=it.price_paise * q))
            sub += it.price_paise * q
        o.subtotal_paise, o.tax_paise = sub, round(sub * 0.05)
        o.total_paise = o.subtotal_paise + o.tax_paise
        if status == OrderStatus.COMPLETED:
            o.payment_status = PaymentStatus.PAID
            o.paid_at = created + timedelta(minutes=1)
            o.accepted_at = created + timedelta(minutes=R.randint(1, 4))
            o.preparing_at = o.accepted_at + timedelta(minutes=1)
            o.ready_at = o.accepted_at + timedelta(minutes=R.randint(6, 25))
            o.completed_at = o.ready_at + timedelta(minutes=R.randint(1, 10))
            o.rating = R.choice([None, 4, 5, 5, 3])
            if o.rating:
                k.rating_sum += o.rating
                k.rating_count += 1
        else:
            o.closed_at = created + timedelta(minutes=R.randint(2, 8))
            o.reason = "Item ran out" if status == OrderStatus.REJECTED else "Cancelled by student"
            o.payment_status = PaymentStatus.REFUNDED if method != "CASH" else "VOID"
        db.add(o)
        db.flush()
        o.order_number = f"CB-{1000 + o.id}"
        db.add(Payment(order_id=o.id, method=method, amount_paise=o.total_paise,
                       status=PaymentStatus.PAID if o.payment_status == PaymentStatus.PAID
                       else ("REFUNDED" if o.payment_status == PaymentStatus.REFUNDED else "VOID"),
                       provider_ref=f"seed_pay_{o.id}" if method != "CASH" else None, created_at=created))
        db.add(OrderStatusHistory(order_id=o.id, to_status=status, note="Seeded history", created_at=created))

    db.add_all([
        FeatureFlag(key="cash_payments", enabled=True, description="Allow pay-at-counter orders"),
        FeatureFlag(key="ratings", enabled=True, description="Students can rate completed orders"),
        FeatureFlag(key="scheduled_pickup", enabled=False, description="Pickup timeslots (phase 2)"),
        FeatureFlag(key="group_orders", enabled=False, description="Group ordering (phase 2)"),
    ])
    db.commit()
    print(f"Seeded {len(colleges)} colleges, {len(kitchens)} approved kitchens (+1 pending), "
          f"{sum(len(v) for v in items_by_kitchen.values())} menu items, {len(students)} students, 200 orders.")
    if settings.is_local:
        print(f"Login OTP for every account: {settings.otp_test_code}")
    else:
        print("Log in with the OTP_FIXED_CODE from the server's .env (or SMS once a provider is set up).")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load CampusBite demo data.")
    parser.add_argument("--if-empty", action="store_true", help="only seed a database with no colleges yet")
    parser.add_argument("--yes-wipe-everything", action="store_true", help="allow wiping a non-local database")
    args = parser.parse_args()
    main(if_empty=args.if_empty, wipe_confirmed=args.yes_wipe_everything)
