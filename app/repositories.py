from datetime import datetime, timedelta
import secrets
from sqlalchemy.orm import Session

from .models import LinkCode, UserPreference
from .settings import settings


def get_user_preferences(db: Session, user_id: int) -> dict:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        return {
            "solver_model": settings.default_model,
            "synth_model": settings.default_model,
            "critic_model": "",
            "checker_model": "",
        }
    return {
        "solver_model": pref.solver_model,
        "synth_model": pref.synth_model,
        "critic_model": pref.critic_model,
        "checker_model": pref.checker_model,
    }


def save_user_preferences(
    db: Session,
    user_id: int,
    solver_model: str,
    synth_model: str,
    critic_model: str,
    checker_model: str,
) -> None:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        pref = UserPreference(user_id=user_id)
        db.add(pref)

    pref.solver_model = solver_model
    pref.synth_model = synth_model
    pref.critic_model = critic_model
    pref.checker_model = checker_model
    pref.updated_at = datetime.utcnow()
    db.commit()


def create_link_code(db: Session, user_id: int, ttl_minutes: int = 5) -> LinkCode:
    code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:8].upper()
    rec = LinkCode(
        code=code,
        user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
        status="active",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def consume_valid_link_code(db: Session, code: str) -> LinkCode | None:
    now = datetime.utcnow()
    rec = (
        db.query(LinkCode)
        .filter(
            LinkCode.code == code.upper(),
            LinkCode.status == "active",
            LinkCode.expires_at > now,
        )
        .first()
    )
    if not rec:
        return None

    rec.status = "consumed"
    rec.consumed_at = now
    db.commit()
    db.refresh(rec)
    return rec


def get_link_code(db: Session, code: str) -> LinkCode | None:
    return db.query(LinkCode).filter(LinkCode.code == code.upper()).first()
