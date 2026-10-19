import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import errors, models  # noqa: F401  (models registers tables)
from .config import settings
from .db import SessionLocal, engine
from .deps import principal_from_token
from .migrate import upgrade_db
from .realtime import hub
from .routers import admin, auth, kitchen, payments, student
from .worker import loop_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.check_production()
    if settings.run_migrations:
        await asyncio.to_thread(upgrade_db)  # applies pending Alembic migrations
    await hub.start()
    task = asyncio.create_task(loop_forever()) if settings.run_worker else None
    yield
    if task:
        task.cancel()
    await hub.stop()


app = FastAPI(title="CampusBite API", version="1.0.0", lifespan=lifespan,
              description="College food ordering & smart canteen management — local MVP.")
errors.install(app)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["x-request-id"])

for r in (auth.router, student.router, kitchen.router, admin.router, payments.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.env, "database": engine.dialect.name,
            "realtime": "redis" if hub._redis_sync else "in-process"}


@app.websocket("/v1/realtime")
async def realtime(ws: WebSocket):
    """The first frame must be {"type": "auth", "token": "<access token>"}: keeping the
    token out of the URL keeps it out of proxy and access logs.
    Rooms: user:{id} always; kitchen:{id} for each kitchen membership; admin for admins.
    Events carry order_id, type, version and ts — clients refetch over REST."""
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=10)
        token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    except Exception:  # not JSON, timeout, or the client went away
        token = None
    p = None
    if isinstance(token, str) and token:
        with SessionLocal() as db:
            p = principal_from_token(db, token)
            if p:
                rooms = [f"user:{p.id}"] + [f"kitchen:{k}" for k in p.kitchen_ids()]
                if p.is_super_admin:
                    rooms.append("admin")
    if not p:
        await ws.close(code=4401)
        return
    await hub.connect(ws, rooms)
    await ws.send_json({"type": "hello", "rooms": rooms})
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)
