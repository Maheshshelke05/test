"""Admin console: every page, moderation, money, support, config and scoping."""
import re

from conftest import admin_login, button, expect, menu_item, student_login, toast

ADMIN = "9000000000"


def test_login_rejects_non_admin_and_every_page_loads(open_app):
    page = open_app("admin")
    admin_login(page, "9800000001")
    expect(page.get_by_text("This account does not have admin access.")).to_be_visible()
    page.reload()
    admin_login(page)
    expect(page.get_by_text("Orders (24h)")).to_be_visible()
    expect(page.get_by_text("Live", exact=True)).to_be_visible()
    for name, marker in [
        ("Live orders", "Filter by college"),
        ("Kitchens", "Review applications"),
        ("Colleges", "Campuses where CampusBite operates"),
        ("Students & users", "Search accounts"),
        ("Payments & refunds", "Sandbox mode"),
        ("Reports", "Gross order value is not business income"),
        ("Support", "Student issues linked to orders"),
        ("Audit log", "High-impact changes"),
        ("Configuration", "Rollout feature flags"),
        ("Dashboard", "Last 24 hours"),
    ]:
        page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile(f"^{re.escape(name)}")).click()
        expect(page.get_by_text(marker, exact=False).first).to_be_visible()
        expect(page.get_by_role("alert")).to_have_count(0)
    # Hash routing survives a reload.
    page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Reports")).click()
    page.reload()
    expect(page.get_by_text("Gross order value is not business income", exact=False)).to_be_visible()


def test_live_orders_search_drawer_and_cancel_refund(open_app, api):
    o = api.order("9800000025", 2, [("Adrak Chai", 1)], method="MOCK_UPI")
    api.post(f"/v1/orders/{o['id']}/pay", "9800000025", json={"outcome": "success"})
    page = open_app("admin")
    admin_login(page)
    page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Live orders")).click()
    page.get_by_label("Search order number").fill(o["order_number"])
    row = page.get_by_role("row").filter(has_text=o["order_number"])
    expect(row).to_have_count(1)
    expect(row.get_by_text("paid")).to_be_visible()
    row.click()
    drawer = page.get_by_role("dialog")
    expect(drawer.get_by_role("heading", name=o["order_number"])).to_be_visible()
    expect(drawer.get_by_text("Status history")).to_be_visible()
    page.once("dialog", lambda d: d.accept("Customer asked to cancel"))
    drawer.get_by_role("button", name="Cancel order & refund").click()
    toast(page, "Order cancelled; refund initiated if paid")
    expect(drawer.get_by_text("Refund · Cancelled by CampusBite: Customer asked to cancel")).to_be_visible()
    drawer.get_by_role("button", name="Close ✕").click()
    expect(page.get_by_role("dialog")).to_have_count(0)

    page.get_by_label("Search order number").fill("")
    page.get_by_label("Status", exact=True).select_option("CANCELLED")
    expect(page.get_by_role("row").filter(has_text=o["order_number"])).to_have_count(1)
    page.get_by_label("Payment status").select_option("PAID")
    expect(page.get_by_role("row").filter(has_text=o["order_number"])).to_have_count(0)
    student = api.get(f"/v1/orders/{o['id']}", "9800000025")
    assert student["status"] == "CANCELLED" and student["payment_status"] in ("REFUND_PENDING", "REFUNDED")


def test_kitchen_moderation(open_app, api):
    api.post("/v1/kitchens/register", "9844400001", json={"college_id": 2, "name": "Test Tiffin", "fssai_number": "12345678901234"})
    page = open_app("admin")
    admin_login(page)
    page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Kitchens")).click()
    row = page.get_by_role("row").filter(has_text="Test Tiffin")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Approve").click()
    toast(page, "Test Tiffin: approved")
    expect(page.get_by_role("row").filter(has_text="Test Tiffin")).to_have_count(0)

    button(page, "approved", exact=True).click()
    row = page.get_by_role("row").filter(has_text="Test Tiffin")
    page.once("dialog", lambda d: d.accept("Hygiene inspection pending"))
    row.get_by_role("button", name="Suspend").click()
    toast(page, "Test Tiffin: suspended")
    button(page, "suspended", exact=True).click()
    row = page.get_by_role("row").filter(has_text="Test Tiffin")
    expect(row.get_by_text("Hygiene inspection pending")).to_be_visible()
    kid = api.get("/v1/admin/kitchens", ADMIN, params={"q": "Test Tiffin"})["items"][0]["id"]
    assert api.get(f"/v1/kitchens/{kid}", ok=False).get("error", {}).get("code") == "NOT_FOUND"
    row.get_by_role("button", name="Approve").click()
    toast(page, "Test Tiffin: approved")
    assert api.get(f"/v1/kitchens/{kid}")["name"] == "Test Tiffin"

    # Cancelling the reason prompt changes nothing.
    button(page, "approved", exact=True).click()
    page.once("dialog", lambda d: d.dismiss())
    page.get_by_role("row").filter(has_text="Test Tiffin").get_by_role("button", name="Suspend").click()
    assert api.get("/v1/admin/kitchens", ADMIN, params={"q": "Test Tiffin"})["items"][0]["status"] == "APPROVED"


def test_colleges_add_edit_deactivate(open_app, api):
    page = open_app("admin")
    admin_login(page)
    page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Colleges")).click()
    button(page, "+ Add college").click()
    drawer = page.get_by_role("dialog")
    drawer.get_by_label("Name").fill("Greenfield College")
    drawer.get_by_label("Short code").fill("gfc")
    drawer.get_by_label("City").fill("Nagpur")
    drawer.get_by_label("Latitude").fill("21.14")
    drawer.get_by_label("Longitude").fill("79.08")
    drawer.get_by_role("button", name="Save").click()
    toast(page, "College saved")
    row = page.get_by_role("row").filter(has_text="Greenfield College")
    expect(row.get_by_text("GFC", exact=True)).to_be_visible()

    row.get_by_role("button", name="Edit").click()
    drawer = page.get_by_role("dialog")
    expect(drawer.get_by_label("Short code")).to_be_disabled()
    drawer.get_by_label("City").fill("Nagpur City")
    drawer.get_by_role("button", name="Save").click()
    toast(page, "College saved")
    row = page.get_by_role("row").filter(has_text="Greenfield College")
    expect(row.get_by_text("Nagpur City")).to_be_visible()
    row.get_by_role("button", name="Deactivate").click()
    expect(row.get_by_text("inactive")).to_be_visible()
    assert all(c["code"] != "GFC" for c in api.get("/v1/colleges")["items"])
    row.get_by_role("button", name="Activate").click()
    expect(row.get_by_text("active", exact=True)).to_be_visible()
    assert any(c["code"] == "GFC" for c in api.get("/v1/colleges")["items"])

    # Duplicate code is refused with a clear message.
    button(page, "+ Add college").click()
    drawer = page.get_by_role("dialog")
    drawer.get_by_label("Name").fill("Copy")
    drawer.get_by_label("Short code").fill("GFC")
    drawer.get_by_role("button", name="Save").click()
    toast(page, "College code already exists")


def test_users_flag_suspend_reactivate(open_app, api):
    page = open_app("admin")
    admin_login(page)
    page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Students & users")).click()
    page.get_by_label("Search users").fill("9800000028")
    row = page.get_by_role("row").filter(has_text="9800000028")
    expect(row).to_have_count(1)
    page.once("dialog", lambda d: d.accept("Repeated fake orders"))
    row.get_by_role("button", name="Flag").click()
    toast(page, "User flagged")
    expect(row.get_by_text("flagged", exact=True)).to_be_visible()
    page.get_by_label("Flag filter").select_option("true")
    expect(page.get_by_role("row").filter(has_text="9800000028")).to_have_count(1)
    page.get_by_label("Flag filter").select_option("")

    page.once("dialog", lambda d: d.accept("Suspending"))
    row.get_by_role("button", name="Suspend").click()
    toast(page, "User suspended")
    expect(row.get_by_text("suspended")).to_be_visible()
    r = api.http.post("/v1/auth/otp/request", json={"phone": "9800000028"})
    r = api.http.post("/v1/auth/otp/verify", json={"phone": "9800000028", "code": "123456"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_SUSPENDED"

    page.once("dialog", lambda d: d.accept(""))
    row.get_by_role("button", name="Reactivate").click()
    toast(page, "User reactivated")
    page.once("dialog", lambda d: d.accept(""))
    row.get_by_role("button", name="Unflag").click()
    toast(page, "Flag cleared")
    r = api.http.post("/v1/auth/otp/request", json={"phone": "9800000028"})
    assert api.http.post("/v1/auth/otp/verify", json={"phone": "9800000028", "code": "123456"}).status_code == 200


def test_payments_reports_csv_support_audit(open_app, api):
    t = api.post("/v1/support", "9800000025", json={"category": "PAYMENT", "message": "Charged twice for chai"})
    page = open_app("admin")
    admin_login(page)
    nav = page.get_by_role("navigation", name="Main")

    nav.get_by_role("button", name=re.compile("^Payments & refunds")).click()
    expect(page.get_by_role("columnheader", name="Payment")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Refund")).to_be_visible()
    page.get_by_label("Payment status").select_option("PAID")
    expect(page.get_by_role("row").filter(has_text="MOCK_UPI").first).to_be_visible()

    nav.get_by_role("button", name=re.compile("^Reports")).click()
    expect(page.get_by_role("row").filter(has_text="Campus Canteen")).to_be_visible()
    with page.expect_download() as dl:
        button(page, "⬇ Export orders CSV").click()
    path = dl.value.path()
    with open(path, encoding="utf-8") as f:
        lines = f.read().strip().splitlines()
    assert lines[0].startswith("order_number,created_at_utc") and len(lines) > 100
    assert dl.value.suggested_filename == "campusbite-orders-30d.csv"

    nav.get_by_role("button", name=re.compile("^Support")).click()
    row = page.get_by_role("row").filter(has_text="Charged twice for chai")
    row.click()
    drawer = page.get_by_role("dialog")
    expect(drawer.get_by_role("heading", name=f"Ticket #{t['id']}")).to_be_visible()
    drawer.get_by_label("Resolution note (visible to student)").fill("Duplicate charge refunded")
    drawer.get_by_role("button", name="Resolve & notify").click()
    toast(page, f"Ticket #{t['id']} → resolved")
    expect(page.get_by_role("row").filter(has_text="Charged twice for chai")).to_have_count(0)
    mine = api.get("/v1/support", "9800000025")["items"]
    assert next(x for x in mine if x["id"] == t["id"])["admin_note"] == "Duplicate charge refunded"

    nav.get_by_role("button", name=re.compile("^Audit log")).click()
    expect(page.get_by_text("support.updated").first).to_be_visible()
    expect(page.get_by_text("report.exported").first).to_be_visible()


def test_feature_flag_blocks_cash_in_student_app(open_app, api):
    page = open_app("admin")
    admin_login(page)
    page.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Configuration")).click()
    card = page.locator(".card").filter(has_text="cash_payments")
    card.get_by_role("button", name="On").click()
    toast(page, "cash_payments disabled")
    try:
        student = open_app("student")
        student_login(student, "9800000025")
        button(student, "Campus Canteen, open").click()
        menu_item(student, "Poha").get_by_role("button", name="Add to cart").click()
        button(student, re.compile(r"^View cart")).click()
        student.get_by_role("radio", name=re.compile("Pay at counter")).click()
        button(student, re.compile(r"^Place order")).click()
        toast(student, "Pay at counter is not available right now")
    finally:
        card.get_by_role("button", name="Off").click()
        toast(page, "cash_payments enabled")


def test_college_admin_is_scoped(open_app):
    page = open_app("admin")
    admin_login(page, "9000000001")
    expect(page.get_by_text("College admin")).to_be_visible()
    nav = page.get_by_role("navigation", name="Main")
    for hidden in ("Payments & refunds", "Audit log", "Configuration"):
        expect(nav.get_by_role("button", name=re.compile(f"^{re.escape(hidden)}"))).to_have_count(0)
    nav.get_by_role("button", name=re.compile("^Colleges")).click()
    expect(page.get_by_role("row").filter(has_text="North Campus Institute of Technology")).to_be_visible()
    expect(page.get_by_role("row").filter(has_text="Riverside College of Commerce")).to_have_count(0)
    expect(button(page, "+ Add college")).to_have_count(0)
    page.get_by_role("button", name="Log out").click()
    expect(page.get_by_label("Admin mobile number")).to_be_visible()
