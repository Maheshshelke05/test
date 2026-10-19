"""Cross-app journeys: three apps open at once, updates arrive live without reloads."""
import re

import qrcode

from conftest import (
    BUILD,
    admin_login,
    button,
    expect,
    kitchen_login,
    launch,
    menu_item,
    order_card,
    student_login,
    toast,
)


def _student_places_order(student, kitchen, items, method):
    button(student, f"{kitchen}, open").click()
    for name, qty in items:
        row = menu_item(student, name)
        row.get_by_role("button", name="Add to cart").click()
        for _ in range(qty - 1):
            row.get_by_label("Increase quantity").click()
    button(student, re.compile(r"^View cart")).click()
    if method == "CASH":
        student.get_by_role("radio", name=re.compile("Pay at counter")).click()
        button(student, re.compile(r"^Place order")).click()
    else:
        button(student, re.compile(r"^Proceed to pay")).click()
        expect(student.get_by_text("SANDBOX GATEWAY", exact=False)).to_be_visible()
    title = student.get_by_text(re.compile(r"^Order CB-\d+$"))
    if method == "CASH":
        expect(title).to_be_visible()
        return title.inner_text().split()[-1]
    return None


def _pickup_code(student) -> str:
    label = student.get_by_label(re.compile(r"^Pickup code")).get_attribute("aria-label")
    return "".join(label.split()[2:])


def test_full_order_lifecycle_across_all_three_apps(open_app):
    cashier = open_app("kitchen")
    kitchen_login(cashier, "9200000001")
    expect(cashier.get_by_text("🟢 Live", exact=False)).to_be_visible()
    cook = open_app("kitchen")
    kitchen_login(cook, "9300000001")
    student = open_app("student")
    sockets = []
    student.on("websocket", lambda ws: sockets.append(ws.url))
    student_login(student, "9800000001")
    expect(student.get_by_text("· 🟢 live", exact=False)).to_be_visible()
    # Access tokens never travel in WebSocket URLs (those end up in server logs).
    assert sockets and not any("token" in u for u in sockets), sockets

    number = _student_places_order(student, "Campus Canteen", [("Poha", 2)], "CASH")
    expect(student.get_by_text("⏳ Waiting for kitchen")).to_be_visible()

    card = order_card(cashier, number)
    expect(card).to_be_visible()  # arrived live
    expect(card.get_by_text("Aarav", exact=False)).to_be_visible()
    card.get_by_role("button", name="Accept", exact=True).click()
    button(cashier, "10 min", exact=True).click()

    expect(student.get_by_text("👍 Accepted")).to_be_visible()
    expect(student.get_by_text("Estimated ready in ~10 min", exact=False)).to_be_visible()
    toast(student, "Order accepted")

    button(cook, re.compile(r"^Accepted")).click()
    order_card(cook, number).get_by_role("button", name=re.compile("Start preparing")).click()
    expect(student.get_by_text("👨‍🍳 Preparing")).to_be_visible()
    button(cook, re.compile(r"^Preparing")).click()
    order_card(cook, number).get_by_role("button", name=re.compile("Mark ready")).click()

    expect(student.get_by_text("Show this at", exact=False)).to_be_visible()
    expect(student.get_by_label("Pickup QR code")).to_be_visible()
    code = _pickup_code(student)
    assert re.fullmatch(r"\d{6}", code)

    cashier.get_by_role("tab", name="Pickup").click()
    cashier.get_by_label("Or type the 6-digit pickup code").fill(code)
    button(cashier, "Verify & hand over").click()
    expect(cashier.get_by_text(f"✅ {number} completed")).to_be_visible()
    expect(cashier.get_by_text("Collect ₹73.50 cash")).to_be_visible()

    expect(student.get_by_text("Enjoy your meal!")).to_be_visible()
    student.get_by_label("Rate 5 stars").click()
    toast(student, "Thanks for rating!")
    expect(student.get_by_text("You rated this order")).to_be_visible()
    button(student, "Go back").click()  # order -> kitchen menu
    button(student, "Go back").click()  # kitchen menu -> home
    expect(student.get_by_text("Kitchens on campus")).to_be_visible()
    expect(student.get_by_text(re.compile("Track →|Show code →"))).to_have_count(0)  # no stale active-order banner

    admin = open_app("admin")
    admin_login(admin)
    admin.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Live orders")).click()
    admin.get_by_label("Search order number").fill(number)
    admin.get_by_label("Status", exact=True).select_option("COMPLETED")
    admin.get_by_role("row").filter(has_text=number).click()
    drawer = admin.get_by_role("dialog")
    for step in ("pending acceptance", "accepted", "preparing", "ready", "completed"):
        expect(drawer.get_by_text(step, exact=True).first).to_be_visible()
    expect(drawer.get_by_text("Pickup verified", exact=False)).to_be_visible()


def test_online_order_rejected_is_refunded_live(open_app):
    cashier = open_app("kitchen")
    kitchen_login(cashier, "9200000002")
    student = open_app("student")
    student_login(student, "9800000004")
    _student_places_order(student, "Chai Point Corner", [("Bun Maska", 1)], "MOCK_UPI")
    button(student, "Pay ₹31.50").click()
    expect(student.get_by_text("⏳ Waiting for kitchen")).to_be_visible()
    number = student.get_by_text(re.compile(r"^Order CB-\d+$")).inner_text().split()[-1]

    card = order_card(cashier, number)
    expect(card.get_by_text("PAID", exact=True)).to_be_visible()
    card.get_by_role("button", name="Reject", exact=True).click()
    button(cashier, "Item out of stock").click()
    button(cashier, "Reject order").click()

    expect(student.get_by_text("✖ Rejected")).to_be_visible()
    expect(student.get_by_text("Item out of stock").first).to_be_visible()
    # The worker settles the refund within a few seconds; the screen updates by itself.
    expect(student.get_by_text("₹31.50 refunded to your original payment method", exact=False)).to_be_visible(timeout=30_000)
    toast(student, "Refund processed")


def test_unpaid_order_is_hidden_from_kitchen_until_paid(open_app, api):
    cashier = open_app("kitchen")
    kitchen_login(cashier, "9200000003")
    admin = open_app("admin")
    admin_login(admin)
    admin.get_by_role("navigation", name="Main").get_by_role("button", name=re.compile("^Live orders")).click()

    student = open_app("student")
    student_login(student, "9800000007")
    _student_places_order(student, "Punjabi Dhaba", [("Aloo Paratha", 1)], "MOCK_UPI")
    button(student, "Go back").click()  # leave the gateway without paying
    expect(student.get_by_text("Complete payment to send this order to the kitchen.")).to_be_visible()
    number = student.get_by_text(re.compile(r"^Order CB-\d+$")).inner_text().split()[-1]

    # Admin sees it live (payment pending); the kitchen does not.
    expect(admin.get_by_role("row").filter(has_text=number)).to_be_visible()
    cashier.wait_for_timeout(3000)
    expect(order_card(cashier, number)).to_have_count(0)

    button(student, "Complete payment").click()
    button(student, "Pay ₹63").click()
    expect(student.get_by_text("Payment successful", exact=False)).to_be_visible()
    expect(order_card(cashier, number)).to_be_visible()
    toast(cashier, f"New order {number}")


def _qr_video(payload: str, path):
    """A Y4M clip (what Chromium's fake camera plays) showing the pickup QR."""
    from PIL import Image

    w, h = 640, 480
    qr = qrcode.make(payload, box_size=8, border=4).convert("L")
    frame = Image.new("L", (w, h), 255)
    frame.paste(qr, ((w - qr.width) // 2, (h - qr.height) // 2))
    y = frame.tobytes()
    uv = bytes([128]) * (w * h // 4)
    with open(path, "wb") as f:
        f.write(f"YUV4MPEG2 W{w} H{h} F10:1 Ip A1:1 C420jpeg\n".encode())
        for _ in range(10):
            f.write(b"FRAME\n" + y + uv + uv)


def test_cashier_scans_student_qr_with_camera(open_app, api, pw):
    order = api.order("9800000017", 6, [("Garlic Bread", 1)])
    api.advance(order, "READY", "9200000006", "9300000006")
    code = api.get(f"/v1/orders/{order['id']}/pickup-code", "9800000017")["code"]
    video = BUILD / "pickup-qr.y4m"
    _qr_video(f"CBPICKUP:{order['id']}:{code}", video)

    camera_browser = launch(pw, ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                                 f"--use-file-for-fake-video-capture={video}"])
    try:
        page = open_app("kitchen", permissions=["camera"], on=camera_browser)
        kitchen_login(page, "9200000006")
        page.get_by_role("tab", name="Pickup").click()
        button(page, "Scan student's QR").click()
        expect(page.get_by_text(f"✅ {order['order_number']} completed")).to_be_visible(timeout=30_000)
        assert api.get(f"/v1/orders/{order['id']}", "9800000017")["status"] == "COMPLETED"
    finally:
        camera_browser.close()
