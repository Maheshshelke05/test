"""Coverage for features not exercised in test_mvp.py: sessions, admin operations,
staff permissions, student extras, worker flags, reports and feature flags."""
from datetime import timedelta

from conftest import idem, login

from app import worker
from app.db import SessionLocal
from app.models import Order
from test_mvp import CASHIER1, COOK1, OWNER1, STUDENT, item_id, place

ADMIN, COLLEGE_ADMIN = "9000000000", "9000000001"


def _ready_order(client, s, cashier, cook):
    o = place(client, s, method="CASH").json()
    o = client.post(f"/v1/kitchen/orders/{o['id']}/accept", headers=cashier, json={"version": o["version"]}).json()
    o = client.patch(f"/v1/kitchen/orders/{o['id']}/status", headers=cook, json={"version": o["version"], "status": "PREPARING"}).json()
    return client.patch(f"/v1/kitchen/orders/{o['id']}/status", headers=cook, json={"version": o["version"], "status": "READY"}).json()


def _complete(client, s, cashier, cook):
    o = _ready_order(client, s, cashier, cook)
    code = client.get(f"/v1/orders/{o['id']}/pickup-code", headers=s).json()["code"]
    return client.post("/v1/kitchen/kitchens/1/verify-pickup", headers=cashier, json={"code": code}).json()


# ---------------------------------------------------------------- sessions


def test_refresh_rotates_and_logout_revokes(client):
    client.post("/v1/auth/otp/request", json={"phone": STUDENT})
    tokens = client.post("/v1/auth/otp/verify", json={"phone": STUDENT, "code": "123456"}).json()
    r = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    # The old refresh token is single-use.
    assert client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    h = {"Authorization": f"Bearer {new['access_token']}"}
    assert client.get("/v1/auth/me", headers=h).status_code == 200
    assert client.post("/v1/auth/logout", headers=h).status_code == 200
    assert client.get("/v1/auth/me", headers=h).status_code == 401
    assert client.post("/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_bad_tokens_rejected(client):
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get("/v1/orders", headers={"Authorization": "Basic abc"}).status_code == 401


def test_suspended_user_locked_out_immediately(client):
    admin, s = login(client, ADMIN), login(client, STUDENT)
    users = client.get("/v1/admin/users", headers=admin, params={"q": STUDENT}).json()["items"]
    uid = users[0]["id"]
    assert client.patch(f"/v1/admin/users/{uid}", headers=admin, json={"is_active": False, "note": "abuse"}).status_code == 200
    assert client.get("/v1/auth/me", headers=s).status_code == 401
    client.post("/v1/auth/otp/request", json={"phone": STUDENT})
    r = client.post("/v1/auth/otp/verify", json={"phone": STUDENT, "code": "123456"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_SUSPENDED"
    client.patch(f"/v1/admin/users/{uid}", headers=admin, json={"is_active": True})
    assert login(client, STUDENT)


def test_new_user_onboarding(client):
    h = login(client, "9876500001")
    me = client.get("/v1/auth/me", headers=h).json()
    assert me["name"] is None and me["college_id"] is None and me["roles"][0]["role"] == "student"
    assert client.patch("/v1/me", headers=h, json={"college_id": 999}).status_code == 400
    me = client.patch("/v1/me", headers=h, json={"name": "Neha", "college_id": 2, "year": "SY"}).json()
    assert me["name"] == "Neha" and me["college"]["code"] == "RCC"


# ---------------------------------------------------------------- discovery & student extras


def test_discovery_filters_and_distance(client):
    near = client.get("/v1/colleges", params={"lat": 17.66, "lng": 75.9}).json()["items"]
    assert near[0]["code"] == "RCC" and near[0]["distance_km"] < 5
    assert [c["code"] for c in client.get("/v1/colleges", params={"q": "pune"}).json()["items"]] == ["HSC", "NCIT"]
    ks = client.get("/v1/colleges/1/kitchens").json()["items"]
    assert len(ks) == 3 and all(k["college_id"] == 1 for k in ks)
    assert client.get("/v1/colleges/1/kitchens", params={"q": "chai"}).json()["items"][0]["name"] == "Chai Point Corner"
    assert client.get("/v1/kitchens/10").status_code == 404  # pending kitchen is not public
    pop = client.get("/v1/colleges/1/popular").json()["items"]
    assert pop and all(i["is_popular"] for i in pop)


def test_favorites_notifications_rating_reorder(client):
    s, cashier, cook = login(client, STUDENT), login(client, CASHIER1), login(client, COOK1)
    vada = item_id(client, 1, "Vada Pav")
    assert client.post(f"/v1/me/favorites/{vada}", headers=s).status_code == 200
    assert client.post(f"/v1/me/favorites/{vada}", headers=s).status_code == 200  # idempotent
    assert [i["id"] for i in client.get("/v1/me/favorites", headers=s).json()["items"]] == [vada]
    client.delete(f"/v1/me/favorites/{vada}", headers=s)
    assert client.get("/v1/me/favorites", headers=s).json()["items"] == []

    o = _complete(client, s, cashier, cook)
    assert o["status"] == "COMPLETED"
    n = client.get("/v1/me/notifications", headers=s).json()
    assert n["unread"] >= 4 and {"Order accepted", "Ready for pickup!"} <= {x["title"] for x in n["items"]}
    client.post("/v1/me/notifications/read", headers=s)
    assert client.get("/v1/me/notifications", headers=s).json()["unread"] == 0

    assert client.post(f"/v1/orders/{o['id']}/rate", headers=s, json={"rating": 6}).status_code == 422
    assert client.post(f"/v1/orders/{o['id']}/rate", headers=s, json={"rating": 5}).status_code == 200
    assert client.post(f"/v1/orders/{o['id']}/rate", headers=s, json={"rating": 4}).json()["error"]["code"] == "ALREADY_RATED"

    q = client.post(f"/v1/orders/{o['id']}/reorder", headers=s).json()
    assert q["lines"][0]["menu_item_id"] == vada and q["can_order"]


def test_cannot_rate_or_cancel_out_of_state(client):
    s, cashier = login(client, STUDENT), login(client, CASHIER1)
    o = place(client, s, method="CASH").json()
    assert client.post(f"/v1/orders/{o['id']}/rate", headers=s, json={"rating": 5}).json()["error"]["code"] == "NOT_COMPLETED"
    client.post(f"/v1/kitchen/orders/{o['id']}/accept", headers=cashier, json={"version": o["version"]})
    assert client.post(f"/v1/orders/{o['id']}/cancel", headers=s).json()["error"]["code"] == "CANNOT_CANCEL"
    assert client.get(f"/v1/orders/{o['id']}/pickup-code", headers=s).json()["error"]["code"] == "NOT_READY"


def test_student_cancel_releases_stock_and_voids_payment(client):
    s = login(client, STUDENT)
    maggi = item_id(client, 1, "Cheese Maggi")
    o = place(client, s, items=[{"menu_item_id": maggi, "quantity": 4}], method="CASH").json()
    o = client.post(f"/v1/orders/{o['id']}/cancel", headers=s).json()
    assert o["status"] == "CANCELLED" and o["payment_status"] == "VOID"
    menu = client.get("/v1/kitchen/kitchens/1/menu", headers=login(client, OWNER1)).json()
    assert next(i for i in menu["items"] if i["id"] == maggi)["stock_qty"] == 20


def test_failed_payment_then_retry(client):
    s = login(client, STUDENT)
    o = place(client, s).json()
    r = client.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "fail"}).json()
    assert r["order"]["payment_status"] == "FAILED"
    r = client.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "success"}).json()
    assert r["order"]["payment_status"] == "PAID"
    assert client.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "success"}).json()["error"]["code"] == "ALREADY_PAID"


def test_support_ticket_flow(client):
    s, admin = login(client, STUDENT), login(client, ADMIN)
    other = login(client, "9800000004")
    o = place(client, s, method="CASH").json()
    assert client.post("/v1/support", headers=other, json={"order_id": o["id"], "category": "DELAYED",
                                                          "message": "not mine"}).status_code == 404
    t = client.post("/v1/support", headers=s, json={"order_id": o["id"], "category": "DELAYED", "message": "Still waiting"}).json()
    assert t["status"] == "OPEN"
    assert any(x["id"] == t["id"] for x in client.get("/v1/admin/support", headers=admin).json()["items"])
    client.patch(f"/v1/admin/support/{t['id']}", headers=admin, json={"status": "RESOLVED", "admin_note": "Sorry, refunded"})
    mine = client.get("/v1/support", headers=s).json()["items"][0]
    assert mine["status"] == "RESOLVED" and mine["admin_note"] == "Sorry, refunded"
    assert client.get("/v1/me/notifications", headers=s).json()["items"][0]["title"] == "Support ticket resolved"


# ---------------------------------------------------------------- kitchen staff


def test_staff_permissions_on_menu_and_settings(client):
    owner, cook, cashier = login(client, OWNER1), login(client, COOK1), login(client, CASHIER1)
    poha = item_id(client, 1, "Poha")
    # Cooks may mark sold out / change stock, but not prices or settings.
    assert client.patch(f"/v1/kitchen/menu-items/{poha}", headers=cook, json={"is_available": False}).status_code == 200
    assert client.patch(f"/v1/kitchen/menu-items/{poha}", headers=cook, json={"stock_qty": 5}).status_code == 200
    assert client.patch(f"/v1/kitchen/menu-items/{poha}", headers=cook, json={"price_paise": 1}).status_code == 403
    assert client.patch("/v1/kitchen/kitchens/1", headers=cashier, json={"is_accepting": False}).status_code == 403
    assert client.post("/v1/kitchen/kitchens/1/categories", headers=cook, json={"name": "X"}).status_code == 403
    assert client.get("/v1/kitchen/kitchens/1/reports", headers=cashier).status_code == 403
    item = client.patch(f"/v1/kitchen/menu-items/{poha}", headers=owner, json={"unlimited_stock": True, "is_available": True}).json()
    assert item["stock_qty"] is None and item["is_available"]


def test_menu_crud_with_addons_and_snapshot(client):
    owner, s = login(client, OWNER1), login(client, STUDENT)
    cat = client.post("/v1/kitchen/kitchens/1/categories", headers=owner, json={"name": "Combos"}).json()
    body = {"name": "Maggi Combo", "price_paise": 9900, "category_id": cat["id"], "is_veg": True,
            "addon_groups": [{"name": "Drink", "min_select": 1, "max_select": 1,
                              "choices": [{"name": "Chai", "price_paise": 0}, {"name": "Cold coffee", "price_paise": 3000}]}]}
    item = client.post("/v1/kitchen/kitchens/1/menu-items", headers=owner, json=body).json()
    choice = item["addon_groups"][0]["choices"][1]["id"]
    # Required group enforced.
    r = place(client, s, items=[{"menu_item_id": item["id"], "quantity": 1}], method="CASH")
    assert r.json()["error"]["code"] == "INVALID_OPTIONS"
    o = place(client, s, items=[{"menu_item_id": item["id"], "quantity": 2, "choice_ids": [choice]}], method="CASH").json()
    assert o["subtotal_paise"] == 2 * 12900 and o["items"][0]["options"][0]["name"] == "Cold coffee"
    # Editing or deleting the item later does not change the order snapshot.
    client.patch(f"/v1/kitchen/menu-items/{item['id']}", headers=owner, json={"name": "Renamed", "price_paise": 1})
    client.delete(f"/v1/kitchen/menu-items/{item['id']}", headers=owner)
    snap = client.get(f"/v1/orders/{o['id']}", headers=s).json()
    assert snap["items"][0]["name"] == "Maggi Combo" and snap["items"][0]["unit_price_paise"] == 12900
    assert all(i["id"] != item["id"] for i in client.get("/v1/kitchens/1/menu").json()["items"])
    # Bad option config is rejected.
    bad = dict(body, addon_groups=[{"name": "X", "min_select": 3, "max_select": 1, "choices": [{"name": "a"}]}])
    assert client.post("/v1/kitchen/kitchens/1/menu-items", headers=owner, json=bad).status_code == 400
    assert client.delete(f"/v1/kitchen/categories/{cat['id']}", headers=owner).status_code == 200


def test_accepting_toggle_and_busy_mode(client):
    owner, s = login(client, OWNER1), login(client, STUDENT)
    k = client.patch("/v1/kitchen/kitchens/1", headers=owner, json={"busy_mode": True}).json()
    assert client.get("/v1/kitchens/1").json()["prep_minutes"] == k["base_prep_minutes"] + 10
    client.patch("/v1/kitchen/kitchens/1", headers=owner, json={"is_accepting": False})
    assert place(client, s, method="CASH").json()["error"]["code"] == "KITCHEN_CLOSED"
    client.patch("/v1/kitchen/kitchens/1", headers=owner, json={"is_accepting": True, "busy_mode": False})
    assert place(client, s, method="CASH").status_code == 201


def test_staff_management_rules(client):
    owner, manager_phone = login(client, OWNER1), "9811100001"
    r = client.post("/v1/kitchen/kitchens/1/staff", headers=owner, json={"phone": manager_phone, "name": "Mona", "role": "kitchen_manager"})
    assert r.status_code == 201
    manager = login(client, manager_phone)
    # A manager can add cashiers but not other managers, and cannot remove the owner.
    assert client.post("/v1/kitchen/kitchens/1/staff", headers=manager, json={"phone": "9811100002", "role": "kitchen_manager"}).status_code == 403
    assert client.post("/v1/kitchen/kitchens/1/staff", headers=manager, json={"phone": "9811100002", "role": "kitchen_cashier"}).status_code == 201
    staff = client.get("/v1/kitchen/kitchens/1/staff", headers=manager).json()["items"]
    owner_id = next(x["user_id"] for x in staff if x["role"] == "kitchen_owner")
    assert client.delete(f"/v1/kitchen/kitchens/1/staff/{owner_id}", headers=manager).json()["error"]["code"] == "IS_OWNER"
    me = client.get("/v1/kitchen/me", headers=manager).json()["items"]
    assert me[0]["my_role"] == "kitchen_manager"


def test_kitchen_reports_and_queue_counts(client):
    s, cashier, cook, owner = login(client, STUDENT), login(client, CASHIER1), login(client, COOK1), login(client, OWNER1)
    _complete(client, s, cashier, cook)
    place(client, s, method="CASH")
    r = client.get("/v1/kitchen/kitchens/1/reports", headers=owner, params={"days": 1}).json()
    assert r["completed_orders"] >= 1 and r["net_payout_paise"] == r["gross_sales_paise"] - r["platform_commission_paise"]
    assert len(r["by_hour"]) == 24 and r["top_items"]
    q = client.get("/v1/kitchen/kitchens/1/orders", headers=cashier).json()
    assert q["counts"].get("PENDING_ACCEPTANCE") == 1
    done = client.get("/v1/kitchen/kitchens/1/orders", headers=cashier, params={"status": "COMPLETED"}).json()["items"]
    assert done and done[0]["student"]["phone_last4"] == STUDENT[-4:] and "phone" not in done[0]["student"]


def test_worker_flags_slow_acceptance(client):
    s = login(client, STUDENT)
    o = place(client, s, method="CASH").json()
    with SessionLocal() as db:
        db.get(Order, o["id"]).created_at -= timedelta(minutes=30)
        db.commit()
    assert worker.run_once()["ack_overdue"] == 1
    assert worker.run_once()["ack_overdue"] == 0  # flagged once only
    assert client.get(f"/v1/orders/{o['id']}", headers=s).json()["ack_overdue"] is True
    admin = login(client, ADMIN)
    assert client.get("/v1/admin/dashboard", headers=admin).json()["delayed_orders"] == 1
    assert client.get("/v1/admin/orders", headers=admin, params={"status": "DELAYED"}).json()["total"] == 1


def test_late_payment_after_expiry_is_refunded(client):
    s = login(client, STUDENT)
    o = place(client, s).json()
    with SessionLocal() as db:
        db.get(Order, o["id"]).created_at -= timedelta(minutes=60)
        db.commit()
    worker.run_once()
    from app.services import payments
    with SessionLocal() as db:
        assert payments.process_event(db, payments.mock_gateway_event(db.get(Order, o["id"]), "success")) == "processed"
    assert client.get(f"/v1/orders/{o['id']}", headers=s).json()["payment_status"] == "REFUND_PENDING"
    worker.run_once()
    assert client.get(f"/v1/orders/{o['id']}", headers=s).json()["payment_status"] == "REFUNDED"


# ---------------------------------------------------------------- admin


def test_admin_dashboard_orders_and_cancel(client):
    admin, s = login(client, ADMIN), login(client, STUDENT)
    o = place(client, s).json()
    client.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "success"})
    d = client.get("/v1/admin/dashboard", headers=admin).json()
    assert d["colleges"] == 3 and d["pending_kitchens"] == 1 and len(d["series_7d"]) >= 1
    page = client.get("/v1/admin/orders", headers=admin, params={"q": o["order_number"]}).json()
    assert page["total"] == 1
    h = client.get(f"/v1/admin/orders/{o['id']}/history", headers=admin).json()
    assert h["payments"][0]["status"] == "PAID"
    c = client.post(f"/v1/admin/orders/{o['id']}/cancel", headers=admin, json={"reason": "Kitchen fire drill"}).json()
    assert c["status"] == "CANCELLED" and c["payment_status"] == "REFUND_PENDING"
    assert client.get("/v1/admin/refunds", headers=admin).json()["items"][0]["order_id"] == o["id"]
    assert client.get("/v1/admin/payments", headers=admin, params={"status": "PAID"}).json()["total"] >= 1


def test_college_admin_scope(client):
    cadmin = login(client, COLLEGE_ADMIN)
    assert [c["code"] for c in client.get("/v1/admin/colleges", headers=cadmin).json()["items"]] == ["NCIT"]
    assert {o["college_id"] for o in client.get("/v1/admin/orders", headers=cadmin, params={"status": ""}).json()["items"]} == {1}
    assert client.get("/v1/admin/payments", headers=cadmin).status_code == 403
    assert client.get("/v1/admin/audit-logs", headers=cadmin).status_code == 403
    assert client.post("/v1/admin/colleges", headers=cadmin, json={"name": "X College", "code": "XC"}).status_code == 403
    rows = client.get("/v1/admin/reports/kitchens", headers=cadmin).json()["items"]
    assert {r["college"] for r in rows} == {"North Campus Institute of Technology"}


def test_admin_colleges_and_moderation(client):
    admin = login(client, ADMIN)
    c = client.post("/v1/admin/colleges", headers=admin, json={"name": "Lakeview College", "code": "lvc", "city": "Nashik"}).json()
    assert c["code"] == "LVC"
    assert client.post("/v1/admin/colleges", headers=admin, json={"name": "Dup", "code": "LVC"}).json()["error"]["code"] == "DUPLICATE_CODE"
    client.patch(f"/v1/admin/colleges/{c['id']}", headers=admin, json={"is_active": False})
    assert all(x["code"] != "LVC" for x in client.get("/v1/colleges").json()["items"])
    # Reject the pending kitchen, then suspend an approved one; owner is notified each time.
    r = client.post("/v1/admin/kitchens/10/reject", headers=admin, json={"reason": "FSSAI document missing"}).json()
    assert r["status"] == "REJECTED" and r["status_reason"] == "FSSAI document missing"
    client.post("/v1/admin/kitchens/2/suspend", headers=admin, json={"reason": "Hygiene complaint"})
    assert client.get("/v1/kitchens/2").status_code == 404
    owner2 = login(client, "9100000002")
    assert client.get("/v1/me/notifications", headers=owner2).json()["items"][0]["title"] == "Kitchen suspended"
    client.post("/v1/admin/kitchens/2/approve", headers=admin)
    assert client.get("/v1/kitchens/2").status_code == 200


def test_admin_csv_export_and_audit(client):
    admin = login(client, ADMIN)
    r = client.get("/v1/admin/reports/orders.csv", headers=admin, params={"days": 30})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("order_number,") and len(lines) == 201
    actions = [a["action"] for a in client.get("/v1/admin/audit-logs", headers=admin).json()["items"]]
    assert "report.exported" in actions


def test_feature_flags_cash_and_ratings(client):
    admin, s = login(client, ADMIN), login(client, STUDENT)
    assert client.patch("/v1/admin/flags/cash_payments", headers=admin, json={"enabled": False}).json()["enabled"] is False
    r = place(client, s, method="CASH")
    assert r.status_code == 400 and r.json()["error"]["code"] == "CASH_DISABLED"
    assert place(client, s).status_code == 201  # online still works
    client.patch("/v1/admin/flags/cash_payments", headers=admin, json={"enabled": True})
    client.patch("/v1/admin/flags/ratings", headers=admin, json={"enabled": False})
    o = _complete(client, s, login(client, CASHIER1), login(client, COOK1))
    assert client.post(f"/v1/orders/{o['id']}/rate", headers=s, json={"rating": 5}).json()["error"]["code"] == "RATINGS_DISABLED"
    assert client.patch("/v1/admin/flags/nope", headers=admin, json={"enabled": True}).status_code == 404


def test_validation_errors_are_structured(client):
    s = login(client, STUDENT)
    r = client.post("/v1/orders", headers={**s, **idem()}, json={"kitchen_id": 1, "items": [{"menu_item_id": 1, "quantity": 0}]})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and "items.0.quantity" in err["fields"] and err["request_id"]
    r = client.post("/v1/orders", headers=s, json={"kitchen_id": 1, "items": []})  # missing Idempotency-Key
    assert r.status_code == 422
    assert client.post("/v1/orders/quote", headers=s, json={"kitchen_id": 1, "items": []}).json()["error"]["code"] == "EMPTY_CART"


def test_ack_timer_starts_at_payment_for_online_orders(client):
    s = login(client, STUDENT)
    o = place(client, s).json()
    with SessionLocal() as db:
        db.get(Order, o["id"]).created_at -= timedelta(minutes=12)  # paid late, just before expiry
        db.commit()
    client.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "success"})
    assert worker.run_once()["ack_overdue"] == 0
    with SessionLocal() as db:
        db.get(Order, o["id"]).paid_at -= timedelta(minutes=11)
        db.commit()
    assert worker.run_once()["ack_overdue"] == 1


def test_profile_email_must_be_valid(client):
    s = login(client, STUDENT)
    r = client.patch("/v1/me", headers=s, json={"email": "not-an-email"})
    assert r.status_code == 422 and "email" in r.json()["error"]["fields"]
    assert client.patch("/v1/me", headers=s, json={"email": "aarav@ncit.edu.in"}).json()["email"] == "aarav@ncit.edu.in"
    assert client.patch("/v1/me", headers=s, json={"email": None}).json()["email"] is None


# ---------------------------------------------------------------- production settings


def _production(monkeypatch, **extra):
    from app.config import settings
    values = {"env": "production", "jwt_secret": "x" * 40, "webhook_secret": "prod-webhook-secret-123", **extra}
    for k, v in values.items():
        monkeypatch.setattr(settings, k, v)
    return settings


def test_production_refuses_dev_secrets(monkeypatch):
    import pytest
    from app.config import DEV_JWT_SECRET, settings

    monkeypatch.setattr(settings, "env", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.check_production()
    _production(monkeypatch, otp_fixed_code="123456")
    with pytest.raises(RuntimeError, match="public test code"):
        settings.check_production()
    _production(monkeypatch, otp_fixed_code="48291")
    with pytest.raises(RuntimeError, match="6 digits"):
        settings.check_production()
    _production(monkeypatch, otp_fixed_code="482913")
    settings.check_production()  # fine
    monkeypatch.setattr(settings, "jwt_secret", DEV_JWT_SECRET)
    with pytest.raises(RuntimeError):
        settings.check_production()


def test_pilot_fixed_otp_is_never_echoed(client, monkeypatch):
    _production(monkeypatch, otp_fixed_code="482913")
    r = client.post("/v1/auth/otp/request", json={"phone": "9811122233"}).json()
    assert r["sent"] is True and "dev_code" not in r
    assert client.post("/v1/auth/otp/verify", json={"phone": "9811122233", "code": "123456"}).status_code == 400
    ok = client.post("/v1/auth/otp/verify", json={"phone": "9811122233", "code": "482913"})
    assert ok.status_code == 200 and ok.json()["access_token"]


def test_sms_mode_uses_random_codes(client, monkeypatch):
    sent = []
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "send_otp_sms", lambda phone, code: sent.append((phone, code)))
    _production(monkeypatch, otp_fixed_code=None)
    r = client.post("/v1/auth/otp/request", json={"phone": "9811122244"}).json()
    assert "dev_code" not in r and len(sent) == 1 and sent[0][1].isdigit() and len(sent[0][1]) == 6
    ok = client.post("/v1/auth/otp/verify", json={"phone": "9811122244", "code": sent[0][1]})
    assert ok.status_code == 200


def test_seed_if_empty_and_wipe_guard(client, monkeypatch):
    import pytest
    import seed
    from app.config import settings

    seed.main(if_empty=True)  # already seeded by the fixture: nothing changes
    admin = login(client, ADMIN)
    assert client.get("/v1/admin/dashboard", headers=admin).json()["colleges"] == 3
    monkeypatch.setattr(settings, "env", "production")
    with pytest.raises(SystemExit, match="Refusing to wipe"):
        seed.main()


def test_realtime_fans_out_through_redis(monkeypatch):
    """Production runs several API workers plus a separate worker process; events must
    travel through Redis pub/sub. A shared fake Redis server stands in for the real one."""
    import fakeredis
    import redis
    import redis.asyncio as aioredis
    from fastapi.testclient import TestClient

    import seed
    from app import worker
    from app.config import settings
    from app.main import app
    from app.realtime import hub

    server = fakeredis.FakeServer()
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, url, **kw: fakeredis.FakeRedis(server=server)))
    monkeypatch.setattr(aioredis.Redis, "from_url", classmethod(lambda cls, url, **kw: fakeredis.FakeAsyncRedis(server=server)))
    monkeypatch.setattr(settings, "redis_url", "redis://fake:6379/0")
    seed.main()
    try:
        with TestClient(app) as c:
            assert c.get("/health").json()["realtime"] == "redis"
            s, cashier = login(c, STUDENT), login(c, CASHIER1)
            with c.websocket_connect("/v1/realtime") as ws:
                ws.send_json({"type": "auth", "token": s["Authorization"].split()[1]})
                assert ws.receive_json()["type"] == "hello"
                o = place(c, s).json()  # online order: paid later
                c.post(f"/v1/orders/{o['id']}/pay", headers=s, json={"outcome": "success"})
                c.post(f"/v1/kitchen/orders/{o['id']}/reject", headers=cashier,
                       json={"version": c.get(f"/v1/orders/{o['id']}", headers=s).json()["version"], "reason": "Out of milk"})
                worker.run_once()  # settles the refund; its event must also arrive via Redis
                seen = []
                for _ in range(20):
                    msg = ws.receive_json()
                    seen.append((msg["type"], msg.get("title") or msg.get("status")))
                    if ("notification", "Refund processed") in seen:
                        break
                assert ("order_updated", "REJECTED") in seen and ("notification", "Refund processed") in seen
    finally:
        hub._redis_sync = None
