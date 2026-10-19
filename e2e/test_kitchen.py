"""Kitchen partner app: queue, roles, menu, pickup, staff, reports, hours."""
import re
from datetime import datetime, timedelta, timezone

from conftest import button, eventually, expect, kitchen_login, order_card, toast

IST = timezone(timedelta(hours=5, minutes=30))


def _tab(page, name):
    page.get_by_role("tab", name=name).click()


def test_roles_see_the_right_tools(open_app):
    cook = open_app("kitchen")
    kitchen_login(cook, "9300000004")
    expect(cook.get_by_text("Wrap & Roll", exact=False).first).to_be_visible()
    expect(cook.get_by_text("cook", exact=False).first).to_be_visible()
    expect(cook.get_by_role("tab", name="Pickup")).to_have_count(0)
    expect(cook.get_by_label("Accepting orders")).to_have_count(0)
    _tab(cook, "More")
    expect(button(cook, re.compile("Sales & reports"))).to_have_count(0)
    expect(button(cook, re.compile("Log out"))).to_be_visible()

    cashier = open_app("kitchen")
    kitchen_login(cashier, "9200000004")
    expect(cashier.get_by_role("tab", name="Pickup")).to_be_visible()
    _tab(cashier, "More")
    expect(button(cashier, re.compile("Staff & roles"))).to_have_count(0)

    owner = open_app("kitchen")
    kitchen_login(owner, "9100000004")
    expect(owner.get_by_label("Accepting orders")).to_be_visible()
    _tab(owner, "More")
    for item in ("Sales & reports", "Staff & roles", "Hours & settings"):
        expect(button(owner, re.compile(item))).to_be_visible()


def test_live_queue_reject_and_accept(open_app, api):
    page = open_app("kitchen")
    kitchen_login(page, "9200000004")
    expect(page.get_by_text("No new orders")).to_be_visible()
    expect(page.get_by_text("🟢 Live", exact=False)).to_be_visible()

    first = api.order("9800000002", 4, [("Paneer Tikka Roll", 1)])
    second = api.order("9800000005", 4, [("Egg Roll", 2)])
    # Both appear without a reload, with a toast.
    toast(page, "New order")
    expect(order_card(page, first["order_number"])).to_be_visible()
    expect(order_card(page, second["order_number"])).to_be_visible()
    expect(button(page, "New (2)")).to_be_visible()

    order_card(page, first["order_number"]).get_by_role("button", name="Reject", exact=True).click()
    expect(page.get_by_text(f"Reject {first['order_number']}")).to_be_visible()
    expect(button(page, "Reject order")).to_be_disabled()
    button(page, "Kitchen too busy").click()
    button(page, "Reject order").click()
    expect(order_card(page, first["order_number"])).to_have_count(0)
    rejected = api.get(f"/v1/orders/{first['id']}", "9800000002")
    assert rejected["status"] == "REJECTED" and rejected["reason"] == "Kitchen too busy"

    card = order_card(page, second["order_number"])
    expect(card.get_by_text("COLLECT CASH")).to_be_visible()
    expect(card.get_by_text("Egg Roll")).to_be_visible()
    card.get_by_role("button", name="Accept", exact=True).click()
    button(page, "15 min", exact=True).click()
    expect(order_card(page, second["order_number"])).to_have_count(0)
    button(page, re.compile(r"^Accepted")).click()
    card = order_card(page, second["order_number"])
    expect(card.get_by_text("ETA 15 min", exact=False)).to_be_visible()
    expect(card.get_by_role("button", name=re.compile("Start preparing"))).to_have_count(0)  # cashier can't cook
    assert api.get(f"/v1/orders/{second['id']}", "9800000005")["eta_minutes"] == 15


def test_cook_prepares_and_cashier_hands_over(open_app, api):
    order = api.order("9800000008", 5, [("Orange Juice", 1), ("Fruit Bowl", 1)])
    api.advance(order, "ACCEPTED", "9200000005", "9300000005")

    cook = open_app("kitchen")
    kitchen_login(cook, "9300000005")
    button(cook, re.compile(r"^Accepted")).click()
    card = order_card(cook, order["order_number"])
    expect(card.get_by_role("button", name="Accept", exact=True)).to_have_count(0)
    card.get_by_role("button", name=re.compile("Start preparing")).click()
    expect(order_card(cook, order["order_number"])).to_have_count(0)
    button(cook, re.compile(r"^Preparing")).click()
    order_card(cook, order["order_number"]).get_by_role("button", name=re.compile("Mark ready")).click()
    expect(order_card(cook, order["order_number"])).to_have_count(0)
    assert api.get(f"/v1/orders/{order['id']}", "9800000008")["status"] == "READY"

    cashier = open_app("kitchen")
    kitchen_login(cashier, "9200000005")
    button(cashier, re.compile(r"^Ready")).click()
    order_card(cashier, order["order_number"]).get_by_role("button", name="Verify pickup code").click()
    code_box = cashier.get_by_label("Or type the 6-digit pickup code")
    code_box.fill("111111")
    button(cashier, "Verify & hand over").click()
    expect(cashier.get_by_text("Pickup code does not match")).to_be_visible()
    code = api.get(f"/v1/orders/{order['id']}/pickup-code", "9800000008")["code"]
    code_box.fill(code)
    button(cashier, "Verify & hand over").click()
    expect(cashier.get_by_text(f"✅ {order['order_number']} completed")).to_be_visible()
    expect(cashier.get_by_text("Collect ₹", exact=False)).to_be_visible()
    done = api.get(f"/v1/orders/{order['id']}", "9800000008")
    assert done["status"] == "COMPLETED" and done["payment_status"] == "PAID"
    button(cashier, re.compile(r"^Done")).click()
    expect(order_card(cashier, order["order_number"]).get_by_text("Collected")).to_be_visible()


def test_pickup_tab_code_qr_payload_and_camera_fallback(open_app, api):
    order = api.order("9800000014", 5, [("Watermelon Juice", 1)])
    api.advance(order, "READY", "9200000005", "9300000005")
    code = api.get(f"/v1/orders/{order['id']}/pickup-code", "9800000014")["code"]

    page = open_app("kitchen")
    kitchen_login(page, "9200000005")
    _tab(page, "Pickup")
    # No camera permission: a clear message, typing still works.
    button(page, "Scan student's QR").click()
    expect(page.get_by_text("Camera permission denied", exact=False)).to_be_visible()
    box = page.get_by_label("Or type the 6-digit pickup code")
    box.fill("000000")
    button(page, "Verify & hand over").click()
    expect(page.get_by_text("No ready order matches this code")).to_be_visible()
    box.fill(f"CBPICKUP:{order['id']}:{code}")
    button(page, "Verify & hand over").click()
    expect(page.get_by_text(f"✅ {order['order_number']} completed")).to_be_visible()


def test_owner_cancels_accepted_order(open_app, api):
    order = api.order("9800000011", 4, [("Veg Frankie", 1)])
    api.advance(order, "ACCEPTED", "9200000004", "9300000004")
    page = open_app("kitchen")
    kitchen_login(page, "9100000004")
    button(page, re.compile(r"^Accepted")).click()
    order_card(page, order["order_number"]).get_by_role("button", name="Cancel order").click()
    dialog = page.get_by_role("alert")
    expect(dialog.get_by_text(f"Cancel {order['order_number']}?")).to_be_visible()
    dialog.get_by_role("button", name="Cancel order").click()
    expect(order_card(page, order["order_number"])).to_have_count(0)
    o = api.get(f"/v1/orders/{order['id']}", "9800000011")
    assert o["status"] == "CANCELLED" and o["reason"] == "Cancelled by kitchen"


def test_menu_availability_stock_edit_and_new_item(open_app, api):
    owner = "9100000005"
    juice = api.item(5, "Orange Juice")
    page = open_app("kitchen")
    kitchen_login(page, owner)
    _tab(page, "Menu")
    expect(page.get_by_text("20 items · 0 sold out")).to_be_visible()
    page.get_by_label("Find an item").fill("orange")
    row = page.get_by_test_id("menu-row").filter(has_text="Orange Juice")
    expect(row).to_have_count(1)

    try:
        row.get_by_label("Orange Juice available").click()
        toast(page, "Orange Juice marked sold out")
        assert api.item(5, "Orange Juice")["sold_out"] is True
        row.get_by_label("Orange Juice available").click()
        toast(page, "Orange Juice is back on")

        row.get_by_text("∞ Unlimited stock · edit").click()
        page.get_by_label("Portions left (leave empty for unlimited)").fill("3")
        button(page, "Save", exact=True).click()
        expect(row.get_by_text("3 portions left · edit")).to_be_visible()
        row.get_by_text("3 portions left · edit").click()
        button(page, "Set unlimited").click()
        expect(row.get_by_text("∞ Unlimited stock · edit")).to_be_visible()

        row.get_by_label("Edit Orange Juice").click()
        expect(page.get_by_text("Edit item", exact=True)).to_be_visible()
        page.get_by_label("Price (₹) *").fill("65")
        button(page, "Save changes").click()
        toast(page, "Item updated")
        expect(page.get_by_test_id("menu-row").filter(has_text="Orange Juice").get_by_text("₹65")).to_be_visible()
        assert api.item(5, "Orange Juice")["price_paise"] == 6500
    finally:
        api.patch(f"/v1/kitchen/menu-items/{juice['id']}", owner, json={"price_paise": 6000, "is_available": True, "unlimited_stock": True})

    page.get_by_label("Find an item").fill("")
    button(page, "+ Category").click()
    page.get_by_placeholder("e.g. Beverages").fill("Combos")
    button(page, "Add category").click()
    expect(page.get_by_text("Combos · 0")).to_be_visible()

    button(page, "+ Item").click()
    page.get_by_label("Item name *").fill("Lassi Combo")
    page.get_by_label("Price (₹) *").fill("99")
    button(page, "Combos", exact=True).click()
    button(page, "Add option group (size, extras…)").click()
    page.get_by_label("Option group name").fill("Size")
    button(page, "Required · pick 1").click()
    page.get_by_label("Choice name").first.fill("Regular")
    page.get_by_text("+ Add choice").click()
    page.get_by_label("Choice name").nth(1).fill("Large")
    page.get_by_label("Extra price in rupees").nth(1).fill("20")
    button(page, "Publish item").click()
    toast(page, "Item added to menu")
    new_row = page.get_by_test_id("menu-row").filter(has_text="Lassi Combo")
    expect(new_row.get_by_text("1 option group", exact=False)).to_be_visible()
    item = api.item(5, "Lassi Combo")
    group = item["addon_groups"][0]
    assert item["price_paise"] == 9900 and group["min_select"] == 1 and group["max_select"] == 1
    assert [(c["name"], c["price_paise"]) for c in group["choices"]] == [("Regular", 0), ("Large", 2000)]

    new_row.get_by_label("Edit Lassi Combo").click()
    button(page, "Delete item").click()
    page.get_by_role("alert").get_by_role("button", name="Delete").click()
    toast(page, "Item deleted")
    expect(page.get_by_test_id("menu-row").filter(has_text="Lassi Combo")).to_have_count(0)


def test_staff_invite_login_and_removal(open_app):
    page = open_app("kitchen")
    kitchen_login(page, "9100000006")
    _tab(page, "More")
    button(page, re.compile("Staff & roles")).click()
    expect(page.get_by_text("Pizza Hub Cashier")).to_be_visible()
    page.get_by_label("Mobile number").fill("9822200001")
    page.get_by_label("Name", exact=True).fill("Riya Helper")
    button(page, "Add staff member").click()
    toast(page, "Staff added")
    expect(page.get_by_text("Riya Helper")).to_be_visible()

    helper = open_app("kitchen")
    kitchen_login(helper, "9822200001")
    expect(helper.get_by_text("Pizza Hub", exact=False).first).to_be_visible()
    expect(helper.get_by_text("cashier", exact=False).first).to_be_visible()

    _tab(helper, "Orders")
    button(page, "Remove Riya Helper").click()
    page.get_by_role("alert").get_by_role("button", name="Remove").click()
    expect(page.get_by_text("Riya Helper")).to_have_count(0)
    # The helper's open app notices on its next refresh, without a reload.
    expect(helper.get_by_text("You’re not linked to a kitchen yet")).to_be_visible(timeout=30_000)


def test_reports_weekly_hours_and_holidays(open_app, api):
    page = open_app("kitchen")
    kitchen_login(page, "9100000006")
    _tab(page, "More")
    button(page, re.compile("Sales & reports")).click()
    expect(page.get_by_text("Gross sales")).to_be_visible()
    expect(page.get_by_text("Your net payout")).to_be_visible()
    button(page, "30 days").click()
    expect(page.get_by_text("Top items")).to_be_visible()
    expect(page.get_by_text("Peak hours (orders)")).to_be_visible()
    button(page, "Today", exact=True).click()
    expect(page.get_by_text("Gross sales")).to_be_visible()
    button(page, "Go back").click()

    button(page, re.compile("Hours & settings")).click()
    expect(page.get_by_text("Weekly hours", exact=True)).to_be_visible()
    today = datetime.now(IST)
    close_chips = button(page, "Close", exact=True)
    expect(close_chips).to_have_count(7)
    try:
        close_chips.nth(today.weekday()).click()
        button(page, "Save weekly hours").click()
        toast(page, "Weekly hours saved")
        eventually(lambda: api.get("/v1/kitchens/6")["is_open"] is False)
        assert "Opens" in api.get("/v1/kitchens/6")["closed_reason"]
        button(page, "Open", exact=True).click()
        button(page, "Save weekly hours").click()
        eventually(lambda: api.get("/v1/kitchens/6")["is_open"] is True)

        date = today.strftime("%Y-%m-%d")
        page.get_by_label("Date (YYYY-MM-DD)").fill(date)
        button(page, "Exam day").click()
        button(page, "Add closed day").click()
        toast(page, "Closed day added")
        expect(page.get_by_text(f"📅 {date} · Exam day")).to_be_visible()
        assert api.get("/v1/kitchens/6")["closed_reason"].startswith("Exam day")
        page.get_by_label(f"Remove closure on {date}").click()
        toast(page, "Closure removed")
        expect(page.get_by_text("No upcoming closures.")).to_be_visible()
    finally:
        k = api.get("/v1/kitchen/kitchens/6", "9100000006")
        days = [{"weekday": d["weekday"], "opens_at": d["opens_at"], "closes_at": d["closes_at"], "is_closed": False}
                for d in k["weekly_hours"]]
        api.put("/v1/kitchen/kitchens/6/hours", "9100000006", json={"days": days})
        for c in k["closures"]:
            api.call("DELETE", f"/v1/kitchen/kitchens/6/closures/{c['id']}", "9100000006")

    page.get_by_label("Pickup counter location").fill("Food court, counter 1A")
    button(page, "Save settings").click()
    toast(page, "Settings saved")
    assert api.get("/v1/kitchens/6")["counter_location"] == "Food court, counter 1A"


def test_accepting_and_busy_toggles(open_app, api):
    page = open_app("kitchen")
    kitchen_login(page, "9100000006")
    base = api.get("/v1/kitchens/6")["prep_minutes"]
    try:
        page.get_by_label("Accepting orders").click()
        toast(page, "Paused new orders")
        expect(page.get_by_text("Paused", exact=True)).to_be_visible()
        assert api.get("/v1/kitchens/6")["closed_reason"] == "Kitchen is not accepting orders right now"
        page.get_by_label("Accepting orders").click()
        toast(page, "Now accepting orders")
        page.get_by_label("Busy mode").click()
        toast(page, "Busy mode on")
        assert api.get("/v1/kitchens/6")["prep_minutes"] == base + 10
        page.get_by_label("Busy mode").click()
        toast(page, "Busy mode off")
    finally:
        api.patch("/v1/kitchen/kitchens/6", "9100000006", json={"is_accepting": True, "busy_mode": False})
    assert api.get("/v1/kitchens/6")["is_open"] is True


def test_new_vendor_registers_sets_up_menu_and_goes_live(open_app, api):
    page = open_app("kitchen")
    kitchen_login(page, "9833300001")
    expect(page.get_by_text("You’re not linked to a kitchen yet")).to_be_visible()
    button(page, "Register a new kitchen").click()
    button(page, "Submit for approval").click()
    expect(page.get_by_text("Choose your college")).to_be_visible()
    page.get_by_role("radio", name=re.compile("Hilltop Science College")).click()
    page.get_by_label("Your name").fill("Suresh")
    page.get_by_label("Kitchen name *").fill("Dosa Corner")
    page.get_by_label("Cuisine").fill("South Indian")
    page.get_by_label("Pickup counter location").fill("Near library")
    button(page, "Submit for approval").click()
    toast(page, "Application submitted for approval")
    expect(page.get_by_text("Awaiting CampusBite approval", exact=False)).to_be_visible()

    _tab(page, "Menu")
    button(page, "+ Category").click()
    page.get_by_placeholder("e.g. Beverages").fill("Dosa")
    button(page, "Add category").click()
    button(page, "+ Item").click()
    page.get_by_label("Item name *").fill("Masala Dosa")
    page.get_by_label("Price (₹) *").fill("70")
    button(page, "Publish item").click()
    toast(page, "Item added to menu")

    kitchens = api.get("/v1/admin/kitchens", "9000000000", params={"q": "Dosa Corner"})["items"]
    assert kitchens[0]["status"] == "PENDING" and kitchens[0]["owner"]["name"] == "Suresh"
    kid = kitchens[0]["id"]
    assert all(k["id"] != kid for k in api.get("/v1/colleges/3/kitchens")["items"])
    api.post(f"/v1/admin/kitchens/{kid}/approve", "9000000000")
    menu = api.get(f"/v1/kitchens/{kid}/menu")
    assert [i["name"] for i in menu["items"]] == ["Masala Dosa"]

    page.reload()
    _tab(page, "Orders")
    expect(page.get_by_text("No new orders")).to_be_visible()
    expect(page.get_by_text("Awaiting CampusBite approval", exact=False)).to_have_count(0)


def test_rejected_vendor_sees_reason(open_app, api):
    api.post("/v1/kitchens/register", "9833300002", json={"college_id": 2, "name": "Shady Snacks"})
    kid = api.get("/v1/admin/kitchens", "9000000000", params={"q": "Shady Snacks"})["items"][0]["id"]
    api.post(f"/v1/admin/kitchens/{kid}/reject", "9000000000", json={"reason": "FSSAI licence not provided"})
    page = open_app("kitchen")
    kitchen_login(page, "9833300002")
    expect(page.get_by_text("Application not approved")).to_be_visible()
    expect(page.get_by_text("FSSAI licence not provided")).to_be_visible()


def test_offline_start_shows_retry_not_logout(open_app):
    page = open_app("kitchen")
    kitchen_login(page, "9200000004")
    expect(page.get_by_role("tab", name="Orders")).to_be_visible()
    open_app.allow_console.append(re.compile("net::ERR_FAILED"))  # requests we abort below
    page.route("**/v1/**", lambda route: route.abort())
    page.reload()
    expect(page.get_by_text("You’re offline")).to_be_visible()
    page.unroute("**/v1/**")
    button(page, "Try again").click()
    expect(page.get_by_role("tab", name="Orders")).to_be_visible()
