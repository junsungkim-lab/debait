from datetime import datetime, timedelta
import secrets
from sqlalchemy.orm import Session

from .models import LinkCode, UserPreference, PipelineStage
from .settings import settings

MAX_PIPELINE_STAGES = 6

DEFAULT_STAGES = [
    {
        "name": "Solver",
        "system_prompt": "You are Solver. Provide the best answer with short assumptions and actionable steps. Keep it concise. Always reply in the same language as the question.",
    },
    {
        "name": "Critic",
        "system_prompt": "You are Critic. Attack weaknesses, missing edge cases, and risks in the previous answer. Keep it short and specific. Always reply in the same language as the question.",
    },
    {
        "name": "Checker",
        "system_prompt": "You are Checker. Verify logical consistency of all previous answers and propose minimal fixes. Keep it short. Always reply in the same language as the question.",
    },
]


# ── Pipeline stages ───────────────────────────────────────────────────────────

def get_pipeline_stages(db: Session, user_id: int) -> list[PipelineStage]:
    return (
        db.query(PipelineStage)
        .filter(PipelineStage.user_id == user_id)
        .order_by(PipelineStage.order_index)
        .all()
    )


def ensure_default_pipeline(db: Session, user_id: int) -> None:
    count = db.query(PipelineStage).filter(PipelineStage.user_id == user_id).count()
    if count == 0:
        default_model = settings.default_model
        for i, s in enumerate(DEFAULT_STAGES):
            db.add(PipelineStage(
                user_id=user_id,
                name=s["name"],
                system_prompt=s["system_prompt"],
                model=default_model,
                order_index=i,
            ))
        db.commit()


def save_pipeline_stages(
    db: Session,
    user_id: int,
    names: list[str],
    prompts: list[str],
    models: list[str],
) -> None:
    # 기존 전부 삭제 후 재삽입 (최대 6개 적용)
    db.query(PipelineStage).filter(PipelineStage.user_id == user_id).delete()
    for i, (name, prompt, model) in enumerate(zip(names, prompts, models)):
        if i >= MAX_PIPELINE_STAGES:
            break
        name = name.strip()
        if not name:
            continue
        db.add(PipelineStage(
            user_id=user_id,
            name=name,
            system_prompt=prompt.strip(),
            model=model.strip() or settings.default_model,
            order_index=i,
        ))
    db.commit()


# ── Synth model preference ────────────────────────────────────────────────────

def get_synth_model(db: Session, user_id: int) -> str:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref or not pref.synth_model:
        return settings.default_model
    return pref.synth_model


def save_synth_model(db: Session, user_id: int, synth_model: str) -> None:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        pref = UserPreference(user_id=user_id)
        db.add(pref)
    pref.synth_model = synth_model.strip() or settings.default_model
    pref.updated_at = datetime.utcnow()
    db.commit()


# ── Link codes ────────────────────────────────────────────────────────────────

def get_user_preferences(db: Session, user_id: int) -> dict:
    return {"synth_model": get_synth_model(db, user_id)}


def save_user_preferences(db, user_id, synth_model="", **_):
    save_synth_model(db, user_id, synth_model)


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
