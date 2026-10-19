"""Realtime fan-out. Events are queued on the DB session with `emit()` and only
published after the transaction commits, so clients never see uncommitted state.

Delivery is best-effort (in-process, or Redis Pub/Sub when REDIS_URL is set);
clients always refetch the canonical order over REST after an event or reconnect."""
import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket
from sqlalchemy import event

from .config import settings
from .db import SessionLocal
from .models import utcnow

log = logging.getLogger("campusbite.realtime")
CHANNEL = "campusbite:events"


class Hub:
    def __init__(self):
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._redis_sync = None
        self._relay_task: asyncio.Task | None = None

    def connect_publisher(self) -> bool:
        """Publish through Redis when configured. Processes that only publish (the standalone
        worker) call this alone; API processes also relay events to their own sockets."""
        if not settings.redis_url:
            return False
        try:
            import redis

            self._redis_sync = redis.Redis.from_url(settings.redis_url)
            self._redis_sync.ping()
            return True
        except Exception as exc:  # fall back to in-process delivery
            log.warning("Redis unavailable (%s); using in-process realtime", exc)
            self._redis_sync = None
            return False

    async def start(self):
        self.loop = asyncio.get_running_loop()
        if self.connect_publisher():
            self._relay_task = asyncio.create_task(self._relay())
            log.info("Realtime using Redis pub/sub")

    async def stop(self):
        if self._relay_task:
            self._relay_task.cancel()

    async def _relay(self):
        import redis.asyncio as aioredis

        while True:  # survive Redis restarts; otherwise this worker would go silent for good
            try:
                pubsub = aioredis.Redis.from_url(settings.redis_url).pubsub()
                await pubsub.subscribe(CHANNEL)
                async for msg in pubsub.listen():
                    if msg.get("type") == "message":
                        data = json.loads(msg["data"])
                        await self._deliver(data["room"], data["message"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Redis relay lost (%s); reconnecting", exc)
                await asyncio.sleep(2)

    async def connect(self, ws: WebSocket, rooms: list[str]):
        for room in rooms:
            self.rooms[room].add(ws)

    def disconnect(self, ws: WebSocket):
        for members in self.rooms.values():
            members.discard(ws)

    async def _deliver(self, room: str, message: dict):
        for ws in list(self.rooms.get(room, ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)

    def publish(self, room: str, message: dict):
        """Thread-safe; callable from sync route handlers."""
        if self._redis_sync is not None:
            try:
                self._redis_sync.publish(CHANNEL, json.dumps({"room": room, "message": message}))
                return
            except Exception as exc:
                log.warning("Redis publish failed: %s", exc)
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._deliver(room, message)))


hub = Hub()


def emit(db, room: str, type_: str, **data):
    data.update(type=type_, ts=utcnow().isoformat() + "Z")
    db.info.setdefault("events", []).append((room, data))


def order_event(db, order, type_: str = "order_updated"):
    payload = dict(order_id=order.id, order_number=order.order_number, status=order.status,
                   payment_status=order.payment_status, version=order.version)
    emit(db, f"user:{order.student_id}", type_, **payload)
    emit(db, f"kitchen:{order.kitchen_id}", type_, **payload)
    emit(db, "admin", type_, **payload)


@event.listens_for(SessionLocal, "after_commit")
def _publish_after_commit(session):
    for room, message in session.info.pop("events", []):
        hub.publish(room, message)


@event.listens_for(SessionLocal, "after_soft_rollback")
def _drop_on_rollback(session, previous_transaction):
    session.info.pop("events", None)
