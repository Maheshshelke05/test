"""Student app, driven like a real user on a phone-sized screen."""
import json
import re

from conftest import OTP, button, expect, menu_item, student_login, toast

# Seeded students: n % 3 == 1 -> North Campus (kitchens 1-3), == 2 -> Riverside (4-6), == 0 -> Hilltop (7-9).


def test_signup_journey_new_student(open_app):
    page = open_app("student")
    expect(page.get_by_text("Skip the canteen queue")).to_be_visible()
    button(page, "Next", exact=True).click()
    expect(page.get_by_text("Every kitchen, one app")).to_be_visible()
    button(page, "Next", exact=True).click()
    expect(page.get_by_text("Track it to the counter")).to_be_visible()
    button(page, "Get started").click()

    phone = page.get_by_label("Mobile number")
    phone.fill("12345")
    expect(button(page, "Continue", exact=True)).to_be_disabled()
    phone.fill("1234567890")
    button(page, "Continue", exact=True).click()
    expect(page.get_by_text("Enter a valid 10-digit mobile number")).to_be_visible()
    phone.fill("9870000001")
    button(page, "Continue", exact=True).click()
    expect(page.get_by_text("Local test mode")).to_be_visible()
    expect(button(page, re.compile(r"Resend OTP in \d+s"))).to_be_disabled()

    page.get_by_label("6-digit OTP").fill("000000")
    button(page, "Verify & continue").click()
    expect(page.get_by_text("Incorrect OTP")).to_be_visible()
    page.get_by_text("Change", exact=True).click()
    expect(page.get_by_label("Mobile number")).to_have_value("9870000001")
    button(page, "Continue", exact=True).click()
    page.get_by_label("6-digit OTP").fill(OTP)
    button(page, "Verify & continue").click()

    expect(page.get_by_text("Tell us about you")).to_be_visible()
    button(page, "Save", exact=True).click()
    expect(page.get_by_text("Please enter your name")).to_be_visible()
    page.get_by_label("Full name *").fill("Test Student")
    page.get_by_label("Roll number (optional)").fill("RCC9001")
    page.get_by_role("radio", name="SY").click()
    button(page, "Save", exact=True).click()

    expect(page.get_by_text("Choose your campus")).to_be_visible()
    page.get_by_placeholder("Search college or city").fill("Solapur")
    expect(button(page, "Choose Riverside College of Commerce")).to_be_visible()
    expect(button(page, "Choose Hilltop Science College")).to_have_count(0)
    button(page, "Choose Riverside College of Commerce").click()
    expect(page.get_by_text("Kitchens on campus")).to_be_visible()
    expect(page.get_by_text("Riverside College of Commerce").first).to_be_visible()
    expect(page.get_by_text(re.compile(r"GOOD (MORNING|AFTERNOON|EVENING), TEST"))).to_be_visible()
    expect(button(page, "Wrap & Roll, open")).to_be_visible()


def test_home_search_and_kitchen_filters(open_app):
    page = open_app("student")
    student_login(page, "9800000001")
    expect(page.get_by_text("North Campus Institute of Technology").first).to_be_visible()

    button(page, "Chai", exact=True).click()
    search = page.get_by_label("Search dishes")
    expect(search).to_have_value("chai")
    expect(page.get_by_text("Adrak Chai")).to_be_visible()
    search.fill("magi")  # typo tolerance
    expect(page.get_by_text("Cheese Maggi").first).to_be_visible()
    search.fill("xyzxyz")
    expect(page.get_by_text("No results for “xyzxyz”")).to_be_visible()
    button(page, "Go back").click()

    page.get_by_text("See all", exact=True).click()
    filter_box = page.get_by_label("Search kitchens")
    filter_box.fill("punjabi")
    expect(button(page, "Punjabi Dhaba, open")).to_be_visible()
    expect(button(page, "Campus Canteen, open")).to_have_count(0)
    filter_box.fill("pizza")
    expect(page.get_by_text("No kitchens match")).to_be_visible()
    button(page, "Clear filters").click()
    for k in ("Campus Canteen", "Chai Point Corner", "Punjabi Dhaba"):
        expect(button(page, f"{k}, open")).to_be_visible()
    button(page, "Open now").click()
    expect(button(page, "Campus Canteen, open")).to_be_visible()

    page.get_by_role("tab", name="Home").click()
    button(page, re.compile(r"^Cheese Maggi from Campus Canteen")).click()
    expect(page.get_by_text("Add-ons")).to_be_visible()  # customisation sheet opens straight away


def test_menu_customisation_steppers_and_favourites(open_app):
    page = open_app("student")
    student_login(page, "9800000004")
    button(page, "Campus Canteen, open").click()
    expect(page.get_by_text("Ground floor, Block A").first).to_be_visible()

    expect(page.get_by_text("Egg Maggi")).to_be_visible()
    button(page, "🟢 Veg only").click()
    expect(page.get_by_text("Egg Maggi")).to_have_count(0)
    button(page, "🟢 Veg only").click()
    expect(page.get_by_text("Egg Maggi")).to_be_visible()

    menu_item(page, "Cheese Maggi").get_by_role("button", name="Add to cart").click()
    expect(page.get_by_text("Add-ons")).to_be_visible()
    page.get_by_role("checkbox", name=re.compile("Extra cheese")).click()
    page.get_by_label("Increase quantity").last.click()
    button(page, "Add item · ₹150").click()
    expect(button(page, "View cart, 2 items, ₹150")).to_be_visible()

    vada = menu_item(page, "Vada Pav")
    vada.get_by_role("button", name="Add to cart").click()
    expect(vada.get_by_label("Quantity 1")).to_be_visible()
    vada.get_by_label("Increase quantity").click()
    expect(vada.get_by_label("Quantity 2")).to_be_visible()
    vada.get_by_label("Decrease quantity").click()
    expect(vada.get_by_label("Quantity 1")).to_be_visible()
    expect(button(page, "View cart, 3 items, ₹170")).to_be_visible()

    vada.get_by_role("button", name="Save Vada Pav to favourites").click()
    expect(vada.get_by_role("button", name="Remove Vada Pav from favourites")).to_be_visible()
    button(page, "Go back").click()
    page.get_by_role("tab", name="Profile").click()
    button(page, "Favourites").click()
    expect(page.get_by_text("Vada Pav")).to_be_visible()
    button(page, "Remove Vada Pav from favourites").click()
    expect(page.get_by_text("No favourites yet")).to_be_visible()
    button(page, "Go back").click()
    page.get_by_role("tab", name="Home").click()
    button(page, "Campus Canteen, open").click()
    # The heart reflects the removal made on another screen.
    expect(menu_item(page, "Vada Pav").get_by_role("button", name="Save Vada Pav to favourites")).to_be_visible()


def test_one_kitchen_cart_replace_dialog(open_app):
    page = open_app("student")
    student_login(page, "9800000007")
    button(page, "Campus Canteen, open").click()
    menu_item(page, "Vada Pav").get_by_role("button", name="Add to cart").click()
    button(page, "Go back").click()
    button(page, "Chai Point Corner, open").click()
    add_chai = menu_item(page, "Adrak Chai").get_by_role("button", name="Add to cart")
    add_chai.click()
    dialog = page.get_by_role("alert")
    expect(dialog.get_by_text("Replace cart?")).to_be_visible()
    dialog.get_by_role("button", name="Cancel").click()
    expect(page.get_by_text("from Campus Canteen")).to_be_visible()
    add_chai.click()
    page.get_by_role("alert").get_by_role("button", name="Replace").click()
    expect(button(page, "View cart, 1 items, ₹20")).to_be_visible()
    expect(page.get_by_text("from Chai Point Corner")).to_be_visible()


def _add_and_open_cart(page, kitchen, items):
    button(page, f"{kitchen}, open").click()
    for name, qty in items:
        row = menu_item(page, name)
        row.get_by_role("button", name="Add to cart").click()
        for _ in range(qty - 1):
            row.get_by_label("Increase quantity").click()
    button(page, re.compile(r"^View cart")).click()
    expect(page.get_by_text("Bill details")).to_be_visible()


def test_online_checkout_failed_then_retry(open_app):
    page = open_app("student")
    student_login(page, "9800000010")
    _add_and_open_cart(page, "Campus Canteen", [("Vada Pav", 2)])
    expect(page.get_by_text("Counter pickup · ASAP")).to_be_visible()
    expect(page.get_by_text("₹42").last).to_be_visible()  # ₹40 + 5% GST
    page.get_by_label("Cooking instructions (optional)").fill("less spicy")
    button(page, "Proceed to pay · ₹42").click()

    expect(page.get_by_text("SANDBOX GATEWAY", exact=False)).to_be_visible()
    button(page, "Simulate failed payment").click()
    expect(page.get_by_text("Payment failed. No money was taken.", exact=False)).to_be_visible()
    button(page, "Retry ₹42").click()
    expect(page.get_by_text("Payment successful", exact=False)).to_be_visible()
    expect(page.get_by_text(re.compile(r"^Order CB-\d+$"))).to_be_visible()
    expect(page.get_by_text("📝 less spicy")).to_be_visible()
    expect(page.get_by_text("UPI (test) · paid")).to_be_visible()
    number = page.get_by_text(re.compile(r"^Order CB-\d+$")).inner_text().split()[-1]

    button(page, "Go back").click()  # order -> kitchen menu
    button(page, "Go back").click()  # kitchen menu -> home
    page.get_by_role("tab", name="Orders").click()
    expect(button(page, re.compile(f"^Order {number}"))).to_be_visible()


def test_cash_order_cancel_and_reorder(open_app):
    page = open_app("student")
    student_login(page, "9800000013")
    _add_and_open_cart(page, "Campus Canteen", [("Poha", 1)])
    page.get_by_role("radio", name=re.compile("Pay at counter")).click()
    button(page, "Place order · ₹36.75").click()
    toast(page, "placed!")
    expect(page.get_by_text("Waiting for kitchen").first).to_be_visible()
    expect(page.get_by_text("The kitchen will accept your order shortly.")).to_be_visible()

    button(page, "Cancel order").click()
    dialog = page.get_by_role("alert")
    expect(dialog.get_by_text("Cancel order?")).to_be_visible()
    dialog.get_by_role("button", name="Keep").click()
    expect(page.get_by_text("Waiting for kitchen").first).to_be_visible()
    button(page, "Cancel order").click()
    page.get_by_role("alert").get_by_role("button", name="Cancel order").click()
    expect(page.get_by_text("Cancelled by student")).to_be_visible()

    button(page, "Reorder").click()
    expect(page.get_by_text("Checkout", exact=True)).to_be_visible()
    expect(page.get_by_text("Poha", exact=True)).to_be_visible()


def test_price_change_and_sold_out_in_cart(open_app, api):
    owner = "9100000003"
    naan, chole = api.item(3, "Butter Naan"), api.item(3, "Chole")
    page = open_app("student")
    student_login(page, "9800000016")
    _add_and_open_cart(page, "Punjabi Dhaba", [("Butter Naan", 1), ("Chole", 1)])
    page.get_by_role("radio", name=re.compile("Pay at counter")).click()
    expect(button(page, "Place order · ₹126")).to_be_visible()
    try:
        api.patch(f"/v1/kitchen/menu-items/{naan['id']}", owner, json={"price_paise": 3500})
        button(page, "Place order · ₹126").click()
        dialog = page.get_by_role("alert")
        expect(dialog.get_by_text("Prices updated")).to_be_visible()
        expect(dialog.get_by_text("₹131.25", exact=False)).to_be_visible()
        dialog.get_by_role("button", name="OK").click()
        expect(page.get_by_text("Price updated to ₹35")).to_be_visible()
        button(page, "Place order · ₹131.25").click()
        expect(page.get_by_text("Waiting for kitchen").first).to_be_visible()

        # Second cart: the item sells out while it sits in the cart.
        button(page, "Go back").click()  # order -> kitchen menu
        button(page, "Go back").click()  # kitchen menu -> home
        _add_and_open_cart(page, "Punjabi Dhaba", [("Chole", 1)])
        button(page, "Go back").click()
        api.patch(f"/v1/kitchen/menu-items/{chole['id']}", owner, json={"is_available": False})
        button(page, re.compile(r"^View cart")).click()
        expect(page.get_by_text("Chole is sold out")).to_be_visible()
        expect(button(page, re.compile(r"^Proceed to pay"))).to_be_disabled()
    finally:
        api.patch(f"/v1/kitchen/menu-items/{naan['id']}", owner, json={"price_paise": 3000})
        api.patch(f"/v1/kitchen/menu-items/{chole['id']}", owner, json={"is_available": True})


def test_closed_kitchen_and_sold_out_badges(open_app):
    page = open_app("student")
    student_login(page, "9800000003")
    closed = button(page, "Desi Thali House, closed")
    expect(closed).to_be_visible()
    expect(closed.get_by_text("CLOSED")).to_be_visible()
    closed.click()
    expect(page.get_by_text("Kitchen is not accepting orders right now").first).to_be_visible()
    expect(page.get_by_text("ordering is paused", exact=False)).to_be_visible()
    menu_item(page, "Pav Bhaji").get_by_role("button", name="Add to cart").click()
    toast(page, "Kitchen is not accepting orders right now")
    expect(button(page, re.compile(r"^View cart"))).to_have_count(0)
    button(page, "Go back").click()
    button(page, "Sweet Tooth Bakery, open").click()
    cheesecake = menu_item(page, "Blueberry Cheesecake")
    expect(cheesecake.get_by_text("SOLD OUT")).to_be_visible()
    expect(cheesecake.get_by_role("button", name="Add to cart")).to_have_count(0)


def test_profile_support_privacy_campus_and_logout(open_app):
    page = open_app("student")
    student_login(page, "9800000019")
    page.get_by_role("tab", name="Profile").click()

    button(page, "Edit profile").click()
    page.get_by_label("College email (optional)").fill("pranav-at-ncit")
    button(page, "Save", exact=True).click()
    expect(page.get_by_text("Enter a valid email or leave it empty")).to_be_visible()
    page.get_by_label("College email (optional)").fill("pranav@ncit.edu.in")
    page.get_by_label("Full name *").fill("Pranav Kulkarni")
    button(page, "Save", exact=True).click()
    toast(page, "Profile saved")
    expect(page.get_by_text("Pranav Kulkarni")).to_be_visible()

    button(page, "Help & support").click()
    button(page, "Missing item").click()
    page.get_by_label("Details").fill("My juice was missing")
    button(page, "Submit ticket").click()
    toast(page, "Ticket raised")
    expect(page.get_by_text(re.compile(r"#\d+ · Missing item"))).to_be_visible()
    expect(page.get_by_text("OPEN", exact=True)).to_be_visible()
    button(page, "Go back").click()

    button(page, "Privacy").click()
    expect(page.get_by_text("What kitchens see")).to_be_visible()
    button(page, "Go back").click()

    button(page, "Notifications").click()
    expect(page.get_by_text("You’re all caught up")).to_be_visible()
    button(page, "Go back").click()

    # Switching campus with a cart from the old campus asks first.
    page.get_by_role("tab", name="Home").click()
    button(page, "Campus Canteen, open").click()
    menu_item(page, "Vada Pav").get_by_role("button", name="Add to cart").click()
    button(page, "Go back").click()
    page.get_by_role("tab", name="Profile").click()
    button(page, "Change campus").click()
    button(page, "Choose Hilltop Science College").click()
    dialog = page.get_by_role("alert")
    expect(dialog.get_by_text("Switch campus?")).to_be_visible()
    dialog.get_by_role("button", name="Cancel").click()
    button(page, "Choose Hilltop Science College").click()
    page.get_by_role("alert").get_by_role("button", name="Switch").click()
    toast(page, "Campus set to Hilltop Science College")
    page.get_by_role("tab", name="Home").click()
    expect(button(page, "Momos Express, open")).to_be_visible()
    expect(button(page, re.compile(r"^View cart"))).to_have_count(0)

    page.get_by_role("tab", name="Profile").click()
    button(page, "Log out").click()
    page.get_by_role("alert").get_by_role("button", name="Log out").click()
    expect(page.get_by_text("Log in or sign up")).to_be_visible()


def test_session_and_cart_survive_reload_and_token_refresh(open_app):
    page = open_app("student")
    student_login(page, "9800000022")
    button(page, "Campus Canteen, open").click()
    menu_item(page, "Vada Pav").get_by_role("button", name="Add to cart").click()
    page.reload()
    expect(page.get_by_text("Kitchens on campus")).to_be_visible()
    expect(button(page, "View cart, 1 items, ₹20")).to_be_visible()

    # An expired/invalid access token is refreshed silently with the refresh token.
    tokens = json.loads(page.evaluate("localStorage.getItem('cb_student_tokens')"))
    tokens["access_token"] = "expired"
    page.evaluate("t => localStorage.setItem('cb_student_tokens', t)", json.dumps(tokens))
    page.reload()
    expect(page.get_by_text("Kitchens on campus")).to_be_visible()
    expect(page.get_by_text("· 🟢 live", exact=False)).to_be_visible()
    refreshed = json.loads(page.evaluate("localStorage.getItem('cb_student_tokens')"))
    assert refreshed["access_token"] != "expired" and refreshed["refresh_token"] != tokens["refresh_token"]

    # With both tokens invalid the user is sent back to login, not stuck on an error.
    page.evaluate("localStorage.setItem('cb_student_tokens', JSON.stringify({access_token: 'x', refresh_token: 'y'}))")
    page.reload()
    expect(page.get_by_text("Log in or sign up")).to_be_visible()


def test_parallel_401s_share_one_token_refresh(open_app):
    """Home fires several requests at once; if they all find the token expired, exactly
    one refresh must happen (refresh tokens are single-use) and the user stays in."""
    page = open_app("student")
    student_login(page, "9800000025")
    page.get_by_role("tab", name="Kitchens").click()
    expect(page.get_by_label("Search kitchens")).to_be_visible()

    expired = {"kitchens": True, "popular": True, "orders": True}
    refreshes = []

    def expire_once(route):
        for key, pending in expired.items():
            if pending and key in route.request.url:
                expired[key] = False
                return route.fulfill(status=401, content_type="application/json",
                                     body='{"error": {"code": "UNAUTHENTICATED", "message": "Session expired"}}')
        return route.continue_()

    page.on("request", lambda r: "/v1/auth/refresh" in r.url and refreshes.append(r.url))
    page.route(re.compile(r".*/v1/(colleges/\d+/(kitchens|popular)|orders\?).*"), expire_once)
    page.get_by_role("tab", name="Home").click()
    expect(page.get_by_text("Kitchens on campus")).to_be_visible()
    expect(button(page, "Campus Canteen, open")).to_be_visible()
    assert not any(expired.values()), expired  # all three really got a 401
    assert len(refreshes) == 1, refreshes


def test_offline_start_shows_retry_not_logout(open_app):
    page = open_app("student")
    student_login(page, "9800000028")
    open_app.allow_console.append(re.compile("net::ERR_FAILED"))  # requests we abort below
    page.route("**/v1/**", lambda route: route.abort())
    page.reload()
    expect(page.get_by_text("You’re offline")).to_be_visible()
    page.unroute("**/v1/**")
    button(page, "Try again").click()
    expect(page.get_by_text("Kitchens on campus")).to_be_visible()
