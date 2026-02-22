from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime

from .settings import settings
from .db import Base, engine, get_db
from .models import User, ApiKey, TelegramLink, Thread, Message, UsageEvent
from .crypto import encrypt_text, decrypt_text
from .telegram import send_message
from .orchestrator.runner import run_orchestrator, Budget
from .repositories import create_link_code, consume_valid_link_code, get_link_code, get_user_preferences, save_user_preferences

app = FastAPI(title="AI Multimodel WebApp + Telegram MVP")
templates = Jinja2Templates(directory="app/templates")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
ser = URLSafeSerializer(settings.session_secret, salt="session")


def create_session(user_id: int) -> str:
    return ser.dumps({"uid": user_id, "ts": datetime.utcnow().isoformat()})


def session_cookie_options() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure,
        "max_age": settings.session_cookie_max_age,
        "path": settings.session_cookie_path,
        "domain": settings.session_cookie_domain,
    }

def read_session(token: str) -> int | None:
    try:
        data = ser.loads(token)
        issued_at_raw = data.get("ts")
        if not issued_at_raw:
            return None
        issued_at = datetime.fromisoformat(issued_at_raw)
        if datetime.utcnow() - issued_at > timedelta(seconds=settings.session_cookie_max_age):
            return None
        return int(data.get("uid"))
    except (BadSignature, Exception):
        return None

def current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get("session")
    if not token:
        return None
    uid = read_session(token)
    if not uid:
        return None
    return db.query(User).filter(User.id == uid).first()

def require_user(request: Request, db: Session) -> User:
    u = current_user(request, db)
    if not u:
        raise HTTPException(status_code=401)
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
    # very small rolling summary. In production, call a cheap summarizer.
    chunk = f"Q: {question}\nA: {answer}\n"
    new = (prev + "\n" + chunk).strip()
    return new[-4000:]  # limit


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=302)

    link_code = create_link_code(db, u.id, ttl_minutes=5)
    webhook_url = f"{settings.base_url}/tg/{settings.webhook_secret}"
    keys = {k.provider: True for k in db.query(ApiKey).filter(ApiKey.user_id == u.id).all()}
    prefs = get_user_preferences(db, u.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "Dashboard",
        "user": u,
        "link_code": link_code.code,
        "webhook_url": webhook_url,
        "keys": keys,
        "prefs": prefs,
    })

@app.get("/conversations", response_class=HTMLResponse)
def conversations(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=302)

    threads = db.query(Thread).filter(Thread.user_id == u.id).order_by(Thread.updated_at.desc()).limit(20).all()
    # attach last 10 messages
    for t in threads:
        t.messages = db.query(Message).filter(Message.thread_id == t.id).order_by(Message.created_at.desc()).limit(10).all()[::-1]
    return templates.TemplateResponse("conversations.html", {"request": request, "title": "Conversations", "user": u, "threads": threads})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Login", "user": None})

@app.post("/login")
def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email.strip().lower()).first()
    if not u or not pwd.verify(password, u.password_hash):
        return RedirectResponse("/login", status_code=302)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session", create_session(u.id), **session_cookie_options())
    return resp

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "title": "Register", "user": None})

@app.post("/register")
def register(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/login", status_code=302)
    u = User(email=email, password_hash=pwd.hash(password))
    db.add(u)
    db.commit()
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session", create_session(u.id), **session_cookie_options())
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session", path=settings.session_cookie_path, domain=settings.session_cookie_domain)
    return resp

@app.post("/keys")
def save_key(request: Request, provider: str = Form(...), api_key: str = Form(...), db: Session = Depends(get_db)):
    u = require_user(request, db)
    provider = provider.strip().lower()
    if provider not in ("openai", "anthropic"):
        raise HTTPException(status_code=400, detail="Unsupported provider")
    enc = encrypt_text(api_key.strip())
    rec = db.query(ApiKey).filter(ApiKey.user_id == u.id, ApiKey.provider == provider).first()
    if not rec:
        rec = ApiKey(user_id=u.id, provider=provider, encrypted_key=enc)
        db.add(rec)
    else:
        rec.encrypted_key = enc
        rec.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/prefs")
def save_prefs(
    request: Request,
    solver_model: str = Form(...),
    synth_model: str = Form(...),
    critic_model: str = Form(""),
    checker_model: str = Form(""),
    db: Session = Depends(get_db),
):
    u = require_user(request, db)
    save_user_preferences(
        db=db,
        user_id=u.id,
        solver_model=solver_model.strip(),
        synth_model=synth_model.strip(),
        critic_model=critic_model.strip(),
        checker_model=checker_model.strip(),
    )
    return RedirectResponse("/", status_code=302)

# --- Telegram webhook ---
@app.post("/tg/{secret}")
async def telegram_webhook(secret: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=404)

    update = await request.json()
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return {"ok": True}

    chat = msg.get("chat", {})
    chat_id = str(chat.get("id"))
    text = (msg.get("text") or "").strip()

    # Quick ACK, process in background
    background.add_task(process_telegram_message, chat_id, text)
    return {"ok": True}

async def process_telegram_message(chat_id: str, text: str):
    # NOTE: using a new DB session per background task
    from .db import SessionLocal
    db = SessionLocal()
    try:
        if text.startswith("/start"):
            await send_message(chat_id, "안녕! 웹앱에서 'Telegram 연결 코드'를 생성한 다음, 그 코드를 그대로 나에게 보내면 연결돼.")
            return

        normalized_text = text.upper() if text else ""

        # Link flow: if message matches an active link code
        if text:
            normalized_code = text.upper()
            code_record = get_link_code(db, normalized_code)
            if code_record:
                if code_record.status == "consumed":
                    await send_message(chat_id, "이미 사용된 연결 코드야. 웹앱에서 새 코드를 생성해줘.")
                    return
                if datetime.utcnow() >= code_record.expires_at:
                    await send_message(chat_id, "연결 코드가 만료됐어. 웹앱에서 새 코드를 생성해줘.")
                    return

                # Link chat_id to user
                existing = db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).first()
                if existing:
                    await send_message(chat_id, "이미 연결되어 있어! 질문을 보내줘.")
                    return

                consumed = consume_valid_link_code(db, normalized_code)
                if not consumed:
                    await send_message(chat_id, "연결 코드가 유효하지 않아. 웹앱에서 새 코드를 생성해줘.")
                    return

                db.add(TelegramLink(user_id=consumed.user_id, chat_id=chat_id))
                db.commit()
                await send_message(chat_id, "연결 완료! 이제 질문을 보내면 AI 단톡방이 답해줄게.")
                return

        # Find user by chat link
        link = db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).first()
        if not link:
            await send_message(chat_id, "아직 웹앱과 연결되지 않았어. 웹앱에서 연결 코드를 만든 뒤 그 코드를 보내줘. (/start)")
            return

        user = db.query(User).filter(User.id == link.user_id).first()
        if not user:
            await send_message(chat_id, "계정 정보를 찾지 못했어. 웹앱에서 다시 로그인/연결해줘.")
            return

        # Thread (telegram chat)
        thread_key = f"telegram:{chat_id}"
        thread = get_or_create_thread(db, user.id, thread_key)

        # Store user message
        db.add(Message(thread_id=thread.id, role="user", content=text))
        db.commit()

        # Load keys & prefs
        keys = get_user_keys(db, user)
        prefs = get_user_preferences(db, user.id)

        models = {
            "solver": prefs.get("solver_model", settings.default_model),
            "critic": prefs.get("critic_model") or prefs.get("solver_model", settings.default_model),
            "checker": prefs.get("checker_model") or prefs.get("solver_model", settings.default_model),
            "synth": prefs.get("synth_model", settings.default_model),
            # gate optional
            "gate": "openai:gpt-4o-mini",
        }

        result = await run_orchestrator(
            question=text,
            thread_summary=thread.summary or "",
            user_api_keys=keys,
            models=models,
            budget=Budget(),
            use_llm_gate=False,
        )

        answer = result.get("final", "").strip() or "(빈 응답)"
        usage = result.get("usage") or {}

        for stage in ("solver", "critic", "checker", "synth"):
            stage_usage = usage.get(stage)
            if not stage_usage:
                continue

            db.add(UsageEvent(
                user_id=user.id,
                provider=(stage_usage.get("provider") or "")[:32],
                model=(stage_usage.get("model") or "")[:64],
                input_tokens=int(stage_usage.get("input_tokens", 0) or 0),
                output_tokens=int(stage_usage.get("output_tokens", 0) or 0),
                cost_usd=float(stage_usage.get("cost_usd", 0.0) or 0.0),
            ))

        # Store assistant message + update summary
        db.add(Message(thread_id=thread.id, role="assistant", content=answer))
        thread.summary = update_summary(thread.summary or "", text, answer)
        thread.updated_at = datetime.utcnow()
        db.commit()

        await send_message(chat_id, answer)

    except Exception as e:
        try:
            await send_message(chat_id, f"처리 중 오류가 났어: {type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        db.close()

@app.get("/health")
def health():
    return PlainTextResponse("ok")
