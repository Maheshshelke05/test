import logging
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..deps import Principal, get_principal
from ..errors import ApiError
from ..models import OtpRequest, Role, Session, User, UserRole, utcnow
from ..schemas import OtpRequestIn, OtpVerifyIn, RefreshIn
from ..security import constant_eq, create_access_token, new_refresh_token, sha256
from ..services.common import college_out, user_out

router = APIRouter(prefix="/v1/auth", tags=["auth"])
log = logging.getLogger("campusbite.auth")


@router.post("/otp/request")
def request_otp(body: OtpRequestIn, db: DbSession = Depends(get_db)):
    since = utcnow() - timedelta(minutes=10)
    recent = db.scalar(select(func.count(OtpRequest.id))
                       .where(OtpRequest.phone == body.phone, OtpRequest.created_at > since))
    if recent >= settings.otp_max_requests_per_10min:
        raise ApiError(429, "OTP_RATE_LIMITED", "Too many OTP requests. Try again in a few minutes.")
    if settings.is_local:
        code = settings.otp_test_code
    elif settings.otp_fixed_code:
        code = settings.otp_fixed_code  # pilot without SMS: shared secret code, never echoed
    else:
        code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(OtpRequest(phone=body.phone, code_hash=sha256(f"{body.phone}:{code}"),
                      expires_at=utcnow() + timedelta(seconds=settings.otp_ttl_seconds)))
    db.commit()
    if not settings.is_local and not settings.otp_fixed_code:
        send_otp_sms(body.phone, code)
    out = {"sent": True, "expires_in": settings.otp_ttl_seconds}
    if settings.is_local:
        out["dev_code"] = code
    return out


def send_otp_sms(phone: str, code: str) -> None:
    """Hook for a real SMS provider (MSG91, Twilio, AWS SNS…). Never log the code itself."""
    log.warning("No SMS provider configured: OTP for ******%s was not delivered", phone[-4:])


def _issue_session(db, user: User) -> dict:
    refresh = new_refresh_token()
    session = Session(user_id=user.id, refresh_hash=sha256(refresh),
                      expires_at=utcnow() + timedelta(days=settings.refresh_token_days))
    db.add(session)
    db.commit()
    return {"access_token": create_access_token(user.id, session.id), "refresh_token": refresh}


def _me(db, user: User) -> dict:
    roles = list(db.scalars(select(UserRole).where(UserRole.user_id == user.id)))
    out = user_out(user, roles)
    out["college"] = college_out(user.college) if user.college else None
    return out


@router.post("/otp/verify")
def verify_otp(body: OtpVerifyIn, db: DbSession = Depends(get_db)):
    otp = db.scalar(select(OtpRequest)
                    .where(OtpRequest.phone == body.phone, OtpRequest.consumed.is_(False))
                    .order_by(OtpRequest.id.desc()))
    if not otp or otp.expires_at < utcnow():
        raise ApiError(400, "OTP_EXPIRED", "OTP expired. Please request a new one.")
    if otp.attempts >= settings.otp_max_verify_attempts:
        raise ApiError(429, "OTP_LOCKED", "Too many wrong attempts. Request a new OTP.")
    if not constant_eq(sha256(f"{body.phone}:{body.code}"), otp.code_hash):
        otp.attempts += 1
        db.commit()
        raise ApiError(400, "OTP_INVALID", "Incorrect OTP", {"code": "Incorrect OTP"})
    otp.consumed = True

    user = db.scalar(select(User).where(User.phone == body.phone))
    is_new = user is None
    if is_new:
        user = User(phone=body.phone)
        user.roles = [UserRole(role=Role.STUDENT)]
        db.add(user)
        db.flush()
    if not user.is_active:
        db.commit()
        raise ApiError(403, "ACCOUNT_SUSPENDED", "This account is suspended. Contact support.")
    tokens = _issue_session(db, user)
    return {**tokens, "is_new": is_new or not user.name, "user": _me(db, user)}


@router.post("/refresh")
def refresh(body: RefreshIn, db: DbSession = Depends(get_db)):
    session = db.scalar(select(Session).where(Session.refresh_hash == sha256(body.refresh_token)))
    if not session or session.revoked or session.expires_at < utcnow():
        raise ApiError(401, "UNAUTHENTICATED", "Session expired, please log in again")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise ApiError(401, "UNAUTHENTICATED", "Session expired, please log in again")
    new_refresh = new_refresh_token()  # rotate on every use
    session.refresh_hash = sha256(new_refresh)
    db.commit()
    return {"access_token": create_access_token(user.id, session.id), "refresh_token": new_refresh}


@router.post("/logout")
def logout(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    session = db.get(Session, p.session_id)
    session.revoked = True
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(p: Principal = Depends(get_principal), db: DbSession = Depends(get_db)):
    return _me(db, p.user)
