"""End-to-end and QA-matrix scenarios from the PRD (sections 15, 20, 22)."""
import threading

from conftest import idem, login

from app.config import settings
from app.db import SessionLocal
from app.models import MenuItem, Order
from app.services import payments
from app import worker

STUDENT = "9800000001"  # Aarav, North Campus (college 1)
OTHER_COLLEGE_STUDENT = "9800000002"  # college 2
OWNER1, CASHIER1, COOK1 = "9100000001", "9200000001", "9300000001"  # Campus Canteen (kitchen 1)
OWNER4 = "9100000004"  # kitchen 4, college 2


def item_id(client, kitchen_id: int, name: str) -> int:
    menu = client.get(f"/v1/kitchens/{kitchen_id}/menu").json()
    return next(i["id"] for i in menu["items"] if i["name"] == name)


def place(client, headers, kitchen_id=1, items=None, method="MOCK_UPI", **extra):
    items = items or [{"menu_item_id": item_id(client, kitchen_id, "Vada Pav"), "quantity": 2}]
    return client.post("/v1/orders", headers={**headers, **idem()},
                       json={"kitchen_id": kitchen_id, "items": items, "payment_method": method, **extra})


def test_pilot_walkthrough(client):
    """PRD §22: order two Cheese Maggi, pay, accept, prepare, ready, verify pickup."""
    s = login(client, STUDENT)
    maggi = item_id(client, 1, "Cheese Maggi")
    q = client.post("/v1/orders/quote", headers=s,
                    json={"kitchen_id": 1, "items": [{"menu_item_id": maggi, "quantity": 2}]}).json()
    assert q["subtotal_paise"] == 12000 and q["can_order"]

    r = place(client, s, items=[{"menu_item_id": maggi, "quantity": 2}], expected_total_paise=q["total_paise"])
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "PENDING_ACCEPTANCE" and order["payment_status"] == "PENDING"

    cashier, cook = login(client, CASHIER1), login(client, COOK1)
    # Unpaid online orders are invisible to the kitchen and cannot be accepted.
    assert all(o["id"] != order["id"] for o in client.get("/v1/kitchen/kitchens/1/orders", headers=cashier).json()["items"])
    r = client.post(f"/v1/kitchen/orders/{order['id']}/accept", headers=cashier, json={"version": order["version"]})
    assert r.json()["error"]["code"] == "PAYMENT_PENDING"

    r = client.post(f"/v1/orders/{order['id']}/pay", headers=s, json={"outcome": "success"})
    assert r.json()["order"]["payment_status"] == "PAID"
    v = r.json()["order"]["version"]

    r = client.post(f"/v1/kitchen/orders/{order['id']}/accept", headers=cashier, json={"version": v, "eta_minutes": 12})
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
    # Cashier cannot cook; cook can.
    v = r.json()["version"]
    assert client.patch(f"/v1/kitchen/orders/{order['id']}/status", headers=cashier,
                        json={"version": v, "status": "PREPARING"}).status_code == 403
    r = client.patch(f"/v1/kitchen/orders/{order['id']}/status", headers=cook, json={"version": v, "status": "PREPARING"})
    r = client.patch(f"/v1/kitchen/orders/{order['id']}/status", headers=cook,
                     json={"version": r.json()["version"], "status": "READY"})
    assert r.json()["status"] == "READY"

    code = client.get(f"/v1/orders/{order['id']}/pickup-code", headers=s).json()
    assert len(code["code"]) == 6
    with SessionLocal() as db:  # only a hash is stored, never the code itself
        assert code["code"] not in (db.get(Order, order["id"]).pickup_hash or "")

    # Cook cannot hand over; cashier verifies by QR payload; second use fails.
    assert client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cook,
                       json={"code": code["qr_payload"]}).status_code == 403
    r = client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cashier, json={"code": code["qr_payload"]})
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    r = client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cashier, json={"code": code["qr_payload"]})
    assert r.json()["error"]["code"] == "NOT_READY"

    with SessionLocal() as db:
        assert db.get(MenuItem, maggi).stock_qty == 18
    report = client.get("/v1/kitchen/kitchens/1/reports", headers=login(client, OWNER1)).json()
    assert report["completed_orders"] >= 1
    detail = client.get(f"/v1/orders/{order['id']}", headers=s).json()
    assert detail["status"] == "COMPLETED" and detail["completed_at"]


def test_last_item_race_exactly_one_wins(client):
    with SessionLocal() as db:
        item = db.get(MenuItem, item_id(client, 1, "Cheese Maggi"))
        item.stock_qty = 1
        db.commit()
        mid = item.id
    # Two North Campus students (1 and 4) try to buy the last portion at the same time.
    heads = [login(client, STUDENT), login(client, "9800000004")]
    results = []

    def buy(h):
        results.append(place(client, h, items=[{"menu_item_id": mid, "quantity": 1}], method="CASH").status_code)

    threads = [threading.Thread(target=buy, args=(h,)) for h in heads]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [201, 409]
    with SessionLocal() as db:
        assert db.get(MenuItem, mid).stock_qty == 0


def test_checkout_tapped_twice_creates_one_order(client):
    s = login(client, STUDENT)
    key = idem()
    body = {"kitchen_id": 1, "items": [{"menu_item_id": item_id(client, 1, "Poha"), "quantity": 1}],
            "payment_method": "CASH"}
    a = client.post("/v1/orders", headers={**s, **key}, json=body).json()
    b = client.post("/v1/orders", headers={**s, **key}, json=body).json()
    assert a["id"] == b["id"]
    assert client.get("/v1/orders?active=true", headers=s).json()["total"] == 1


def test_webhook_repeat_is_exactly_once_and_signed(client):
    s = login(client, STUDENT)
    order = place(client, s).json()
    with SessionLocal() as db:
        event = payments.mock_gateway_event(db.get(Order, order["id"]), "success")
    body = payments.event_bytes(event)
    bad = client.post("/v1/payments/webhook", content=body, headers={"X-Signature": "nope"})
    assert bad.status_code == 401
    sig = {"X-Signature": payments.sign(body), "Content-Type": "application/json"}
    assert client.post("/v1/payments/webhook", content=body, headers=sig).json()["result"] == "processed"
    assert client.post("/v1/payments/webhook", content=body, headers=sig).json()["result"] == "duplicate"
    assert client.get(f"/v1/orders/{order['id']}", headers=s).json()["payment_status"] == "PAID"


def test_wrong_pickup_code_keeps_ready_and_throttles(client):
    s, cashier, cook = login(client, STUDENT), login(client, CASHIER1), login(client, COOK1)
    o = place(client, s, method="CASH").json()
    o = client.post(f"/v1/kitchen/orders/{o['id']}/accept", headers=cashier, json={"version": o["version"]}).json()
    o = client.patch(f"/v1/kitchen/orders/{o['id']}/status", headers=cook, json={"version": o["version"], "status": "PREPARING"}).json()
    o = client.patch(f"/v1/kitchen/orders/{o['id']}/status", headers=cook, json={"version": o["version"], "status": "READY"}).json()
    for _ in range(settings.pickup_max_attempts):
        r = client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cashier,
                        json={"code": "000000", "order_id": o["id"]})
        assert r.json()["error"]["code"] in ("INVALID_PICKUP_CODE",)
    r = client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cashier, json={"code": "000000", "order_id": o["id"]})
    assert r.status_code == 429
    assert client.get(f"/v1/orders/{o['id']}", headers=s).json()["status"] == "READY"
    # Student reopening the pickup screen rotates the code and unlocks.
    code = client.get(f"/v1/orders/{o['id']}/pickup-code", headers=s).json()["code"]
    r = client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cashier, json={"code": code})
    assert r.json()["status"] == "COMPLETED" and r.json()["payment_status"] == "PAID"  # cash collected


def test_cross_college_and_cross_kitchen_denied(client):
    other = login(client, OTHER_COLLEGE_STUDENT)
    r = place(client, other)
    assert r.status_code == 403 and r.json()["error"]["code"] == "COLLEGE_MISMATCH"

    s = login(client, STUDENT)
    o = place(client, s, method="CASH").json()
    assert client.get(f"/v1/orders/{o['id']}", headers=other).status_code == 404
    owner4 = login(client, OWNER4)
    assert client.get("/v1/kitchen/kitchens/1/orders", headers=owner4).status_code == 404
    assert client.post(f"/v1/kitchen/orders/{o['id']}/accept", headers=owner4,
                       json={"version": o["version"]}).status_code == 404
    assert client.get("/v1/admin/dashboard", headers=s).status_code == 403


def test_price_change_requires_reconfirmation(client):
    s = login(client, STUDENT)
    poha = item_id(client, 1, "Poha")
    q = client.post("/v1/orders/quote", headers=s, json={"kitchen_id": 1, "items": [{"menu_item_id": poha, "quantity": 1}]}).json()
    owner = login(client, OWNER1)
    client.patch(f"/v1/kitchen/menu-items/{poha}", headers=owner, json={"price_paise": 4000})
    r = place(client, s, items=[{"menu_item_id": poha, "quantity": 1}], expected_total_paise=q["total_paise"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "PRICE_CHANGED"
    assert r.json()["error"]["fields"]["quote"]["subtotal_paise"] == 4000


def test_reject_after_payment_refunds_and_restores_stock(client):
    s, cashier = login(client, STUDENT), login(client, CASHIER1)
    maggi = item_id(client, 1, "Cheese Maggi")
    o = place(client, s, items=[{"menu_item_id": maggi, "quantity": 3}]).json()
    o = client.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "success"}).json()["order"]
    r = client.post(f"/v1/kitchen/orders/{o['id']}/reject", headers=cashier, json={"version": o["version"]})
    assert r.status_code == 422  # reason required
    r = client.post(f"/v1/kitchen/orders/{o['id']}/reject", headers=cashier,
                    json={"version": o["version"], "reason": "Gas cylinder empty"})
    assert r.json()["status"] == "REJECTED" and r.json()["payment_status"] == "REFUND_PENDING"
    with SessionLocal() as db:
        assert db.get(MenuItem, maggi).stock_qty == 20
    worker.run_once()
    assert client.get(f"/v1/orders/{o['id']}", headers=s).json()["payment_status"] == "REFUNDED"


def test_stale_version_conflict(client):
    s, cashier, owner = login(client, STUDENT), login(client, CASHIER1), login(client, OWNER1)
    o = place(client, s, method="CASH").json()
    assert client.post(f"/v1/kitchen/orders/{o['id']}/accept", headers=cashier, json={"version": o["version"]}).status_code == 200
    r = client.post(f"/v1/kitchen/orders/{o['id']}/reject", headers=owner, json={"version": o["version"], "reason": "dup"})
    assert r.status_code == 409


def test_closed_kitchen_and_sold_out(client):
    s = login(client, STUDENT)
    # Kitchen 8 is closed and in college 3; use owner 8's own college via a college-3 student.
    s3 = login(client, "9800000003")
    r = place(client, s3, kitchen_id=8, items=[{"menu_item_id": item_id(client, 8, "Pav Bhaji"), "quantity": 1}])
    assert r.status_code == 409 and r.json()["error"]["code"] == "KITCHEN_CLOSED"
    with SessionLocal() as db:
        db.get(MenuItem, item_id(client, 1, "Poha")).is_available = False
        db.commit()
    r = place(client, s, items=[{"menu_item_id": item_id(client, 1, "Poha"), "quantity": 1}])
    assert r.json()["error"]["code"] == "SOLD_OUT"


def test_addon_validation_and_pricing(client):
    s3 = login(client, "9800000006")  # college 3 (kitchens 7-9)
    menu = client.get("/v1/kitchens/7/menu").json()
    momo = next(i for i in menu["items"] if i["name"] == "Veg Steamed Momos")
    extra = momo["addon_groups"][0]["choices"][0]
    q = client.post("/v1/orders/quote", headers=s3, json={"kitchen_id": 7, "items": [
        {"menu_item_id": momo["id"], "quantity": 2, "choice_ids": [extra["id"]]}]}).json()
    assert q["subtotal_paise"] == 2 * (momo["price_paise"] + extra["price_paise"])
    r = client.post("/v1/orders/quote", headers=s3, json={"kitchen_id": 7, "items": [
        {"menu_item_id": momo["id"], "quantity": 1, "choice_ids": [999999]}]}).json()
    assert r["problems"][0]["code"] == "INVALID_OPTIONS"


def test_kitchen_registration_and_admin_approval(client):
    newbie = login(client, "9876543210")
    r = client.post("/v1/kitchens/register", headers=newbie,
                    json={"college_id": 1, "name": "Dosa Plaza", "cuisine": "South Indian"})
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    kid = r.json()["id"]
    assert client.get(f"/v1/kitchens/{kid}").status_code == 404  # not public yet
    newbie = login(client, "9876543210")  # role list refreshed on each request anyway
    r = client.post(f"/v1/kitchen/kitchens/{kid}/menu-items", headers=newbie,
                    json={"name": "Masala Dosa", "price_paise": 7000})
    assert r.status_code == 201

    cadmin = login(client, "9000000001")  # college admin of college 1
    assert client.post(f"/v1/admin/kitchens/{kid}/approve", headers=cadmin).status_code == 200
    assert client.get(f"/v1/kitchens/{kid}").json()["name"] == "Dosa Plaza"
    # College admin cannot see other colleges' kitchens.
    assert client.post("/v1/admin/kitchens/4/suspend", headers=cadmin, json={"reason": "test it"}).status_code == 404
    admin = login(client, "9000000000")
    logs = client.get("/v1/admin/audit-logs", headers=admin).json()["items"]
    assert any(l["action"] == "kitchen.approved" for l in logs)


def test_removed_staff_loses_access_immediately(client):
    owner, cook = login(client, OWNER1), login(client, COOK1)
    assert client.get("/v1/kitchen/kitchens/1/orders", headers=cook).status_code == 200
    staff = client.get("/v1/kitchen/kitchens/1/staff", headers=owner).json()["items"]
    cook_id = next(x["user_id"] for x in staff if x["role"] == "kitchen_cook")
    assert client.delete(f"/v1/kitchen/kitchens/1/staff/{cook_id}", headers=owner).status_code == 200
    assert client.get("/v1/kitchen/kitchens/1/orders", headers=cook).status_code == 404


def test_unpaid_orders_expire_and_release_stock(client):
    s = login(client, STUDENT)
    maggi = item_id(client, 1, "Cheese Maggi")
    o = place(client, s, items=[{"menu_item_id": maggi, "quantity": 5}]).json()
    with SessionLocal() as db:
        from datetime import timedelta
        order = db.get(Order, o["id"])
        order.created_at -= timedelta(minutes=settings.unpaid_order_expiry_minutes + 1)
        db.commit()
        assert db.get(MenuItem, maggi).stock_qty == 15
    worker.run_once()
    assert client.get(f"/v1/orders/{o['id']}", headers=s).json()["status"] == "CANCELLED"
    with SessionLocal() as db:
        assert db.get(MenuItem, maggi).stock_qty == 20


def test_otp_rate_limit_and_wrong_code(client):
    for _ in range(settings.otp_max_requests_per_10min):
        client.post("/v1/auth/otp/request", json={"phone": "9811111111"})
    assert client.post("/v1/auth/otp/request", json={"phone": "9811111111"}).status_code == 429
    client.post("/v1/auth/otp/request", json={"phone": "9822222222"})
    r = client.post("/v1/auth/otp/verify", json={"phone": "9822222222", "code": "999999"})
    assert r.json()["error"]["code"] == "OTP_INVALID"


def test_search_tolerates_typos(client):
    r = client.get("/v1/colleges/1/search", params={"q": "magi"}).json()
    names = {i["name"] for g in r["results"] for i in g["items"]}
    assert {"Cheese Maggi", "Masala Maggi", "Egg Maggi"} <= names and r["suggestion"] == "maggi"
    r = client.get("/v1/colleges/1/search", params={"q": "chese magi"}).json()
    assert [i["name"] for g in r["results"] for i in g["items"]] == ["Cheese Maggi"]
    r = client.get("/v1/colleges/1/search", params={"q": "xyzxyz"}).json()
    assert r["results"] == [] and r["suggestion"] is None
    # Search never leaks other colleges' kitchens.
    r = client.get("/v1/colleges/1/search", params={"q": "momos"}).json()
    assert all(g["kitchen"]["college_id"] == 1 for g in r["results"])


def test_websocket_receives_order_events(client):
    s = login(client, STUDENT)
    token = s["Authorization"].split()[1]
    cashier = login(client, CASHIER1)
    # The token travels in the first frame, never in the URL (URLs end up in access logs).
    with client.websocket_connect("/v1/realtime") as ws:
        ws.send_json({"type": "auth", "token": token})
        hello = ws.receive_json()
        assert hello["type"] == "hello" and len(hello["rooms"]) == 1 and hello["rooms"][0].startswith("user:")
        o = place(client, s, method="CASH").json()
        client.post(f"/v1/kitchen/orders/{o['id']}/accept", headers=cashier, json={"version": o["version"]})
        types = set()
        for _ in range(6):
            msg = ws.receive_json()
            types.add((msg["type"], msg.get("status")))
            if ("order_updated", "ACCEPTED") in types:
                break
        assert ("order_updated", "ACCEPTED") in types
        ws.send_text("ping")
        assert ws.receive_json()["type"] in ("pong", "notification", "order_updated")


def test_websocket_rejects_missing_or_bad_auth(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    for first in ({"type": "auth", "token": "nonsense"}, {"type": "hello"}, "ping"):
        with client.websocket_connect("/v1/realtime") as ws:
            ws.send_json(first) if isinstance(first, dict) else ws.send_text(first)
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4401
    # Kitchen staff join their kitchen room; super admins join the admin room.
    for phone, room in ((CASHIER1, "kitchen:1"), ("9000000000", "admin")):
        token = login(client, phone)["Authorization"].split()[1]
        with client.websocket_connect("/v1/realtime") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert room in ws.receive_json()["rooms"]


def test_weekly_hours_and_holiday_closure(client):
    from datetime import datetime, timedelta, timezone
    ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    today = ist.strftime("%Y-%m-%d")
    owner, cook, s = login(client, OWNER1), login(client, COOK1), login(client, STUDENT)

    # Closing today via the weekly schedule blocks ordering and says when it reopens.
    days = [{"weekday": d, "opens_at": "00:00", "closes_at": "23:59", "is_closed": d == ist.weekday()} for d in range(7)]
    assert client.put("/v1/kitchen/kitchens/1/hours", headers=cook, json={"days": days}).status_code == 403
    k = client.put("/v1/kitchen/kitchens/1/hours", headers=owner, json={"days": days}).json()
    assert k["weekly_hours"][ist.weekday()]["is_closed"] and k["is_open"] is False
    assert "tomorrow at 00:00" in k["closed_reason"]
    r = place(client, s, method="CASH")
    assert r.json()["error"]["code"] == "KITCHEN_CLOSED"

    # Reopen today, then add a holiday for today: closed with the holiday reason.
    days[ist.weekday()]["is_closed"] = False
    client.put("/v1/kitchen/kitchens/1/hours", headers=owner, json={"days": days})
    assert client.post("/v1/kitchen/kitchens/1/closures", headers=owner,
                       json={"date": "2000-01-01", "reason": "Old"}).status_code == 400
    k = client.post("/v1/kitchen/kitchens/1/closures", headers=owner, json={"date": today, "reason": "Exam day"}).json()
    public = client.get("/v1/kitchens/1").json()
    assert public["is_open"] is False and public["closed_reason"].startswith("Exam day")
    k = client.delete(f"/v1/kitchen/kitchens/1/closures/{k['closures'][0]['id']}", headers=owner).json()
    assert k["is_open"] is True and k["closures"] == []
    assert place(client, s, method="CASH").status_code == 201
