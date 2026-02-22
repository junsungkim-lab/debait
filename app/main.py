from typing import List
from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from .settings import settings
from .db import Base, engine, get_db
from .models import User, ApiKey, TelegramLink, Thread, Message, UsageEvent
from .crypto import encrypt_text, decrypt_text
from .telegram import send_message
from .orchestrator.runner import run_orchestrator, Budget
from .repositories import (
    create_link_code, consume_valid_link_code, get_link_code,
    get_pipeline_stages, save_pipeline_stages, ensure_default_pipeline,
    get_synth_model, save_synth_model,
    MAX_PIPELINE_STAGES,
)

app = FastAPI(title="Debait")
templates = Jinja2Templates(directory="app/templates")

SINGLE_USER_ID = 1


def ensure_single_user(db: Session) -> User:
    u = db.query(User).filter(User.id == SINGLE_USER_ID).first()
    if not u:
        u = User(id=SINGLE_USER_ID, email="single@local", password_hash="")
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


def get_user_keys(db: Session, user: User) -> dict:
    keys = {}
    for k in db.query(ApiKey).filter(ApiKey.user_id == user.id).all():
        try:
            keys[k.provider] = decrypt_text(k.encrypted_key)
        except Exception:
            pass
    return keys


def get_or_create_thread(db: Session, user_id: int, thread_key: str) -> Thread:
    t = db.query(Thread).filter(Thread.user_id == user_id, Thread.thread_key == thread_key).first()
    if not t:
        t = Thread(user_id=user_id, thread_key=thread_key, summary="")
        db.add(t)
        db.commit()
        db.refresh(t)
    return t


def update_summary(prev: str, question: str, answer: str) -> str:
    chunk = f"Q: {question}\nA: {answer}\n"
    return (prev + "\n" + chunk).strip()[-4000:]


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    from .db import SessionLocal
    db = SessionLocal()
    try:
        ensure_single_user(db)
        ensure_default_pipeline(db, SINGLE_USER_ID)
    finally:
        db.close()


# ── Chat ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    ensure_single_user(db)
    keys = {k.provider: True for k in db.query(ApiKey).filter(ApiKey.user_id == SINGLE_USER_ID).all()}
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "Chat · Debait",
        "keys": keys,
        "result": None,
        "question": "",
    })


@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, question: str = Form(...), db: Session = Depends(get_db)):
    u = ensure_single_user(db)
    keys_db   = get_user_keys(db, u)
    keys_flag = {k.provider: True for k in db.query(ApiKey).filter(ApiKey.user_id == SINGLE_USER_ID).all()}

    stages     = get_pipeline_stages(db, SINGLE_USER_ID)
    synth_mdl  = get_synth_model(db, SINGLE_USER_ID)
    stages_dicts = [{"name": s.name, "system_prompt": s.system_prompt, "model": s.model} for s in stages]

    thread_key = f"web:{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    thread = get_or_create_thread(db, SINGLE_USER_ID, thread_key)
    db.add(Message(thread_id=thread.id, role="user", content=question))
    db.commit()

    try:
        result = await run_orchestrator(
            question=question,
            thread_summary=thread.summary or "",
            user_api_keys=keys_db,
            stages=stages_dicts,
            synth_model=synth_mdl,
            budget=Budget(),
            use_llm_gate=False,
        )
    except Exception as e:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "title": "Chat · Debait",
            "keys": keys_flag,
            "result": None,
            "question": question,
            "error": f"{type(e).__name__}: {e}",
        })

    final = result.get("final", "").strip() or "(빈 응답)"

    for sr in result.get("stages", []):
        db.add(Message(thread_id=thread.id, role=sr["name"], content=sr["text"]))
    db.add(Message(thread_id=thread.id, role="assistant", content=final))
    thread.summary = update_summary(thread.summary or "", question, final)
    thread.updated_at = datetime.utcnow()
    db.commit()

    usage = result.get("usage") or {}
    for stage_name, su in usage.items():
        if not su:
            continue
        db.add(UsageEvent(
            user_id=SINGLE_USER_ID,
            provider=(su.get("provider") or "")[:32],
            model=(su.get("model") or "")[:64],
            input_tokens=int(su.get("input_tokens", 0) or 0),
            output_tokens=int(su.get("output_tokens", 0) or 0),
            cost_usd=float(su.get("cost_usd", 0.0) or 0.0),
        ))
    db.commit()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "Chat · Debait",
        "keys": keys_flag,
        "result": result,
        "question": question,
    })


# ── Conversations ─────────────────────────────────────────────────────────────

@app.get("/conversations", response_class=HTMLResponse)
def conversations(request: Request, db: Session = Depends(get_db)):
    ensure_single_user(db)
    threads = (
        db.query(Thread)
        .filter(Thread.user_id == SINGLE_USER_ID)
        .order_by(Thread.updated_at.desc())
        .limit(30)
        .all()
    )
    for t in threads:
        t.messages = (
            db.query(Message)
            .filter(Message.thread_id == t.id)
            .order_by(Message.created_at.asc())
            .all()
        )
    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "title": "History · Debait",
        "threads": threads,
    })


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    ensure_single_user(db)
    link_code   = create_link_code(db, SINGLE_USER_ID, ttl_minutes=5)
    webhook_url = f"{settings.base_url}/tg/{settings.webhook_secret}"
    keys        = {k.provider: True for k in db.query(ApiKey).filter(ApiKey.user_id == SINGLE_USER_ID).all()}
    stages      = get_pipeline_stages(db, SINGLE_USER_ID)
    synth_mdl   = get_synth_model(db, SINGLE_USER_ID)
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "title": "Settings · Debait",
        "link_code": link_code.code,
        "webhook_url": webhook_url,
        "keys": keys,
        "stages": stages,
        "synth_model": synth_mdl,
        "max_stages": MAX_PIPELINE_STAGES,
    })


@app.post("/keys")
def save_key(provider: str = Form(...), api_key: str = Form(...), db: Session = Depends(get_db)):
    ensure_single_user(db)
    provider = provider.strip().lower()
    if provider not in ("openai", "anthropic", "google", "groq", "mistral"):
        raise HTTPException(status_code=400, detail="Unsupported provider")
    enc = encrypt_text(api_key.strip())
    rec = db.query(ApiKey).filter(ApiKey.user_id == SINGLE_USER_ID, ApiKey.provider == provider).first()
    if not rec:
        rec = ApiKey(user_id=SINGLE_USER_ID, provider=provider, encrypted_key=enc)
        db.add(rec)
    else:
        rec.encrypted_key = enc
        rec.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/settings", status_code=302)


@app.post("/pipeline")
def save_pipeline(
    stage_name:   List[str] = Form(default=[]),
    stage_prompt: List[str] = Form(default=[]),
    stage_model:  List[str] = Form(default=[]),
    synth_model:  str       = Form(default=""),
    db: Session = Depends(get_db),
):
    ensure_single_user(db)
    save_pipeline_stages(db, SINGLE_USER_ID, stage_name, stage_prompt, stage_model)
    save_synth_model(db, SINGLE_USER_ID, synth_model)
    return RedirectResponse("/settings#pipeline", status_code=302)


# ── Telegram webhook ──────────────────────────────────────────────────────────

@app.post("/tg/{secret}")
async def telegram_webhook(secret: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=404)

    update = await request.json()
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return {"ok": True}

    chat_id = str(msg.get("chat", {}).get("id"))
    text    = (msg.get("text") or "").strip()
    background.add_task(process_telegram_message, chat_id, text)
    return {"ok": True}


async def process_telegram_message(chat_id: str, text: str):
    from .db import SessionLocal
    db = SessionLocal()
    try:
        if text.startswith("/start"):
            await send_message(chat_id, "안녕! 웹앱에서 'Telegram 연결 코드'를 생성한 다음, 그 코드를 그대로 나에게 보내면 연결돼.")
            return

        if text:
            code_record = get_link_code(db, text.upper())
            if code_record:
                if code_record.status == "consumed":
                    await send_message(chat_id, "이미 사용된 연결 코드야. 웹앱에서 새 코드를 생성해줘.")
                    return
                if datetime.utcnow() >= code_record.expires_at:
                    await send_message(chat_id, "연결 코드가 만료됐어. 웹앱에서 새 코드를 생성해줘.")
                    return
                if db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).first():
                    await send_message(chat_id, "이미 연결되어 있어! 질문을 보내줘.")
                    return
                consumed = consume_valid_link_code(db, text.upper())
                if not consumed:
                    await send_message(chat_id, "연결 코드가 유효하지 않아.")
                    return
                db.add(TelegramLink(user_id=consumed.user_id, chat_id=chat_id))
                db.commit()
                await send_message(chat_id, "연결 완료! 이제 질문을 보내면 AI 단톡방이 답해줄게.")
                return

        link = db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).first()
        if not link:
            await send_message(chat_id, "아직 웹앱과 연결되지 않았어. (/start)")
            return

        user = db.query(User).filter(User.id == link.user_id).first()
        if not user:
            await send_message(chat_id, "계정 정보를 찾지 못했어.")
            return

        thread = get_or_create_thread(db, user.id, f"telegram:{chat_id}")
        db.add(Message(thread_id=thread.id, role="user", content=text))
        db.commit()

        stages     = get_pipeline_stages(db, user.id)
        synth_mdl  = get_synth_model(db, user.id)
        stages_dicts = [{"name": s.name, "system_prompt": s.system_prompt, "model": s.model} for s in stages]

        result = await run_orchestrator(
            question=text,
            thread_summary=thread.summary or "",
            user_api_keys=get_user_keys(db, user),
            stages=stages_dicts,
            synth_model=synth_mdl,
            budget=Budget(),
            use_llm_gate=False,
        )

        final = result.get("final", "").strip() or "(빈 응답)"

        for sr in result.get("stages", []):
            db.add(Message(thread_id=thread.id, role=sr["name"], content=sr["text"]))
        db.add(Message(thread_id=thread.id, role="assistant", content=final))
        thread.summary = update_summary(thread.summary or "", text, final)
        thread.updated_at = datetime.utcnow()

        for stage_name, su in (result.get("usage") or {}).items():
            if not su:
                continue
            db.add(UsageEvent(
                user_id=user.id,
                provider=(su.get("provider") or "")[:32],
                model=(su.get("model") or "")[:64],
                input_tokens=int(su.get("input_tokens", 0) or 0),
                output_tokens=int(su.get("output_tokens", 0) or 0),
                cost_usd=float(su.get("cost_usd", 0.0) or 0.0),
            ))
        db.commit()

        await send_message(chat_id, final)

    except Exception as e:
        try:
            await send_message(chat_id, f"처리 중 오류: {type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        db.close()


@app.get("/health")
def health():
    return PlainTextResponse("ok")
