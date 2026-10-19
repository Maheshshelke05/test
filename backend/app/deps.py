"""Authentication and scope checks. Every protected route resolves a Principal from
the bearer token; roles are re-read from the DB on each request so revoking a role
or suspending a user takes effect immediately."""
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError, forbidden, not_found
from .models import Kitchen, Role, Session, User, UserRole, utcnow
from .security import decode_access_token


@dataclass
class Principal:
    user: User
    session_id: int
    roles: list[UserRole]

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def is_super_admin(self) -> bool:
        return any(r.role == Role.SUPER_ADMIN for r in self.roles)

    def college_admin_ids(self) -> set[int]:
        return {r.college_id for r in self.roles if r.role == Role.COLLEGE_ADMIN and r.college_id}

    def kitchen_role(self, kitchen_id: int) -> str | None:
        for r in self.roles:
            if r.kitchen_id == kitchen_id and r.role in Role.KITCHEN_ROLES:
                return r.role
        return None

    def kitchen_ids(self) -> set[int]:
        return {r.kitchen_id for r in self.roles if r.kitchen_id and r.role in Role.KITCHEN_ROLES}


def principal_from_token(db: DbSession, token: str) -> Principal | None:
    data = decode_access_token(token)
    if not data:
        return None
    session = db.get(Session, data["sid"])
    if not session or session.revoked or session.expires_at < utcnow():
        return None
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active or session.user_id != user.id:
        return None
    roles = list(db.scalars(select(UserRole).where(UserRole.user_id == user.id)))
    return Principal(user=user, session_id=session.id, roles=roles)


def get_principal(
    authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Login required")
    principal = principal_from_token(db, authorization[7:].strip())
    if not principal:
        raise ApiError(401, "UNAUTHENTICATED", "Session expired, please log in again")
    return principal


def require_admin(p: Principal = Depends(get_principal)) -> Principal:
    if not (p.is_super_admin or p.college_admin_ids()):
        raise forbidden()
    return p


def require_super_admin(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_super_admin:
        raise forbidden()
    return p


def admin_college_scope(p: Principal) -> set[int] | None:
    """None means all colleges (super admin)."""
    return None if p.is_super_admin else p.college_admin_ids()


def kitchen_for_staff(db: DbSession, p: Principal, kitchen_id: int, allowed: tuple[str, ...]) -> Kitchen:
    kitchen = db.get(Kitchen, kitchen_id)
    role = p.kitchen_role(kitchen_id)
    if not kitchen or role is None:
        raise not_found("Kitchen")
    if role not in allowed:
        raise forbidden(f"Your role ({role.replace('kitchen_', '')}) cannot do this")
    return kitchen


MANAGE = (Role.KITCHEN_OWNER, Role.KITCHEN_MANAGER)
ALL_STAFF = Role.KITCHEN_ROLES
FRONT_DESK = (Role.KITCHEN_OWNER, Role.KITCHEN_MANAGER, Role.KITCHEN_CASHIER)
COOKING = (Role.KITCHEN_OWNER, Role.KITCHEN_MANAGER, Role.KITCHEN_COOK)
