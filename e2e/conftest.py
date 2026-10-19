"""Browser end-to-end harness.

Builds the three web apps against a dedicated API port, seeds a separate database
(e2e/.build/e2e.db, never your dev DB), starts everything, and drives it with
Playwright like a real user. Run from the repo root:

    backend/.venv/Scripts/python -m pytest e2e -q            # full build + run
    E2E_SKIP_BUILD=1 backend/.venv/Scripts/python -m pytest e2e -q   # reuse last build
    E2E_HEADED=1 ...                                          # watch the browser

Needs Microsoft Edge or Chrome installed (E2E_CHANNEL=msedge|chrome), or run
`playwright install chromium` and set E2E_CHANNEL=chromium.
"""
import functools
import http.server
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "e2e" / ".build"
SHOTS = BUILD / "shots"
API_PORT, STUDENT_PORT, KITCHEN_PORT, ADMIN_PORT = 8100, 8181, 8182, 8130
API = f"http://localhost:{API_PORT}"
STUDENT_URL = f"http://localhost:{STUDENT_PORT}"
KITCHEN_URL = f"http://localhost:{KITCHEN_PORT}"
ADMIN_URL = f"http://localhost:{ADMIN_PORT}"
NPX = "npx.cmd" if os.name == "nt" else "npx"
OTP = "123456"

expect.set_options(timeout=15_000)


# ---------------------------------------------------------------- stack


def _run(cmd, cwd, env):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")


def _build():
    env = {**os.environ, "EXPO_PUBLIC_API_URL": API, "VITE_API_URL": API}
    for app in ("student", "kitchen"):
        _run([NPX, "expo", "export", "--platform", "web", "--clear", "--output-dir", str(BUILD / app)], ROOT / "apps" / app, env)
    _run([NPX, "vite", "build", "--outDir", str(BUILD / "admin"), "--emptyOutDir"], ROOT / "apps" / "admin", env)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _serve(directory: Path, port: int):
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", port), functools.partial(_Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _wait(url: str, seconds: int = 60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


@pytest.fixture(scope="session", autouse=True)
def stack():
    BUILD.mkdir(exist_ok=True)
    SHOTS.mkdir(exist_ok=True)
    if not os.environ.get("E2E_SKIP_BUILD") or not (BUILD / "admin" / "index.html").exists():
        _build()
    db = BUILD / "e2e.db"
    for f in BUILD.glob("e2e.db*"):
        f.unlink()
    env = {
        **os.environ,
        "ENV": "local",
        "DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "OTP_MAX_REQUESTS_PER_10MIN": "10000",  # many logins per phone across the suite
        "WORKER_INTERVAL_SECONDS": "2",
        "RUN_WORKER": "true",
    }
    env.pop("REDIS_URL", None)  # in-process realtime keeps the harness self-contained
    _run([sys.executable, "seed.py"], ROOT / "backend", env)
    log = open(BUILD / "api.log", "w", encoding="utf-8")
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)],
                           cwd=ROOT / "backend", env=env, stdout=log, stderr=subprocess.STDOUT)
    servers = [_serve(BUILD / "student", STUDENT_PORT), _serve(BUILD / "kitchen", KITCHEN_PORT),
               _serve(BUILD / "admin", ADMIN_PORT)]
    try:
        _wait(f"{API}/health")
        for url in (STUDENT_URL, KITCHEN_URL, ADMIN_URL):
            _wait(url)
        yield
    finally:
        api.terminate()
        api.wait(10)
        log.close()
        for s in servers:
            s.shutdown()


# ---------------------------------------------------------------- API helper (test setup only)


class Api:
    """Direct API access to arrange state the way another user would."""

    def __init__(self):
        self.http = httpx.Client(base_url=API, timeout=15)
        self._tokens: dict[str, dict] = {}

    def auth(self, phone: str) -> dict:
        if phone not in self._tokens:
            self.http.post("/v1/auth/otp/request", json={"phone": phone}).raise_for_status()
            r = self.http.post("/v1/auth/otp/verify", json={"phone": phone, "code": OTP})
            r.raise_for_status()
            self._tokens[phone] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return self._tokens[phone]

    def call(self, method: str, path: str, phone: str | None = None, ok: bool = True, **kw):
        headers = {**(self.auth(phone) if phone else {}), **kw.pop("headers", {})}
        r = self.http.request(method, path, headers=headers, **kw)
        if ok and r.status_code >= 400:
            raise AssertionError(f"{method} {path} -> {r.status_code} {r.text}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    def get(self, path, phone=None, **kw):
        return self.call("GET", path, phone, **kw)

    def post(self, path, phone=None, **kw):
        return self.call("POST", path, phone, **kw)

    def patch(self, path, phone=None, **kw):
        return self.call("PATCH", path, phone, **kw)

    def put(self, path, phone=None, **kw):
        return self.call("PUT", path, phone, **kw)

    def item(self, kitchen_id: int, name: str) -> dict:
        return next(i for i in self.get(f"/v1/kitchens/{kitchen_id}/menu")["items"] if i["name"] == name)

    def order(self, phone: str, kitchen_id: int, items: list[tuple[str, int]], method: str = "CASH") -> dict:
        lines = [{"menu_item_id": self.item(kitchen_id, n)["id"], "quantity": q} for n, q in items]
        return self.post("/v1/orders", phone, headers={"Idempotency-Key": f"e2e-{time.time_ns()}"},
                         json={"kitchen_id": kitchen_id, "items": lines, "payment_method": method})

    def advance(self, order: dict, to: str, cashier: str, cook: str) -> dict:
        """Move an order forward through the kitchen flow up to `to` (ACCEPTED/PREPARING/READY)."""
        o = order
        if o["status"] == "PENDING_ACCEPTANCE":
            o = self.post(f"/v1/kitchen/orders/{o['id']}/accept", cashier, json={"version": o["version"]})
        for step in ("PREPARING", "READY"):
            if o["status"] == to:
                break
            o = self.patch(f"/v1/kitchen/orders/{o['id']}/status", cook, json={"version": o["version"], "status": step})
        return o


@pytest.fixture(scope="session")
def api():
    return Api()


# ---------------------------------------------------------------- browser


@pytest.fixture(scope="session")
def pw():
    with sync_playwright() as p:
        yield p


def launch(pw, args=None):
    channel = os.environ.get("E2E_CHANNEL", "msedge")
    return pw.chromium.launch(channel=None if channel == "chromium" else channel,
                              headless=not os.environ.get("E2E_HEADED"), args=args or [])


@pytest.fixture(scope="session")
def browser(pw):
    b = launch(pw)
    yield b
    b.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


IGNORED_CONSOLE = (
    re.compile(r"Failed to load resource: the server responded with a status of 4\d\d"),  # expected API errors
    re.compile(r"WebSocket connection to .* failed"),  # reconnects while the API restarts a socket
)

VIEWPORTS = {"student": (400, 860), "kitchen": (800, 1000), "admin": (1366, 900)}


@pytest.fixture()
def open_app(browser, request):
    """open_app("student"|"kitchen"|"admin") -> a fresh page in its own browser profile."""
    pages, problems = [], []

    def _open(kind: str, permissions=None, on=None):
        w, h = VIEWPORTS[kind]
        ctx = (on or browser).new_context(viewport={"width": w, "height": h}, permissions=permissions or [],
                                          accept_downloads=True)
        page = ctx.new_page()
        tag = f"{kind}#{len(pages) + 1}"
        page.on("pageerror", lambda e: problems.append(f"[{tag}] uncaught: {e}"))
        page.on("console", lambda m: m.type == "error" and not any(p.search(m.text) for p in IGNORED_CONSOLE)
                and problems.append(f"[{tag}] console.error: {m.text}"))
        page.goto({"student": STUDENT_URL, "kitchen": KITCHEN_URL, "admin": ADMIN_URL}[kind])
        pages.append((tag, page))
        return page

    # Tests that break the network on purpose can whitelist the resulting console noise.
    _open.allow_console = []
    yield _open

    problems[:] = [p for p in problems if not any(a.search(p) for a in _open.allow_console)]
    failed = getattr(request.node, "rep_call", None) and request.node.rep_call.failed
    for tag, page in pages:
        if failed:
            safe = re.sub(r"[^\w.-]+", "_", f"{request.node.name}-{tag}")
            try:
                page.screenshot(path=str(SHOTS / f"{safe}.png"))
            except Exception:
                pass
        page.context.close()
    if problems and not failed:
        pytest.fail("Browser errors:\n" + "\n".join(problems))


# ---------------------------------------------------------------- UI helpers


def button(page, name, exact=False):
    return page.get_by_role("button", name=name, exact=exact)


def student_login(page, phone: str, expect_home: bool = True):
    skip = button(page, "Skip", exact=True)
    expect(skip.or_(page.get_by_label("Mobile number")).first).to_be_visible()
    if skip.count():
        skip.click()
    page.get_by_label("Mobile number").fill(phone)
    button(page, "Continue", exact=True).click()
    page.get_by_label("6-digit OTP").fill(OTP)
    button(page, "Verify & continue").click()
    if expect_home:
        expect(page.get_by_text("Kitchens on campus")).to_be_visible()


def kitchen_login(page, phone: str):
    page.get_by_label("Mobile number").fill(phone)
    button(page, "Send OTP").click()
    page.get_by_label("OTP", exact=True).fill(OTP)
    button(page, "Verify", exact=True).click()


def admin_login(page, phone: str = "9000000000"):
    page.get_by_label("Admin mobile number").fill(phone)
    button(page, "Send OTP").click()
    page.get_by_label(re.compile("OTP sent")).fill(OTP)
    button(page, "Sign in").click()


def menu_item(page, name: str):
    return page.get_by_test_id("menu-item").filter(has=page.get_by_text(name, exact=True))


def order_card(page, order_number: str):
    return page.get_by_test_id("order-card").filter(has_text=order_number)


def eventually(check, timeout: float = 15.0):
    """Poll a server-side condition; UI toasts can be stale when the same text repeats."""
    deadline = time.time() + timeout
    while not check():
        if time.time() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.25)


def toast(page, text):
    return expect(page.get_by_text(text, exact=False).first).to_be_visible()
