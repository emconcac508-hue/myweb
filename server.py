"""SentinelJar 4.0 - server (FastAPI + SQLite).

Tài khoản admin được tạo từ biến môi trường ADMIN_USER / ADMIN_PASS khi server khởi động,
không nằm trong code hay trong trang web.
"""
import hashlib
import json
import os
import re
import secrets
import smtplib
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data.db"
MUSIC_DIR = BASE / "music"
STATIC_DIR = BASE / "static"
MUSIC_DIR.mkdir(exist_ok=True)

COOKIE = "sj_token"
SESSION_DAYS = 30
MAX_MUSIC = 30 * 1024 * 1024
AUDIO_EXT = {".mp3", ".ogg", ".wav", ".m4a"}
PLAN_NAMES = {1: "BASIC", 2: "PRO", 3: "ELITE"}
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
# Cloudflare Turnstile (để trống cả hai = tắt xác minh)
TS_SITE = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
TS_SECRET = os.environ.get("TURNSTILE_SECRET", "").strip()
# Gmail gửi OTP (SMTP_PASS là "Mật khẩu ứng dụng" 16 ký tự của Google). Để trống = OTP chỉ in ra cửa sổ CMD.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").replace(" ", "")
OTP_TTL = 600


# ---------- database ----------
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def run(sql, args=(), fetch=None):
    with closing(conn()) as c:
        cur = c.execute(sql, args)
        out = cur.fetchall() if fetch == "all" else cur.fetchone() if fetch == "one" else None
        c.commit()
        return out


def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def init():
    with closing(conn()) as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY COLLATE NOCASE, email TEXT,
                salt TEXT, pw TEXT, plan INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS keys(code TEXT PRIMARY KEY, plan INTEGER, used_by TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS pending(email TEXT PRIMARY KEY COLLATE NOCASE, username TEXT, salt TEXT, pw TEXT,
                code_hash TEXT, expires REAL, tries INTEGER DEFAULT 0, last_sent REAL);
            CREATE TABLE IF NOT EXISTS gates(token TEXT PRIMARY KEY, created REAL);
            CREATE TABLE IF NOT EXISTS music(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, filename TEXT);
            """
        )
        if ADMIN_USER and ADMIN_PASS:
            salt = secrets.token_hex(16)
            c.execute(
                "INSERT INTO users(username,email,salt,pw,plan,is_admin) VALUES(?,?,?,?,3,1) "
                "ON CONFLICT(username) DO UPDATE SET salt=excluded.salt, pw=excluded.pw, plan=3, is_admin=1",
                (ADMIN_USER, "", salt, hash_pw(ADMIN_PASS, salt)),
            )
        c.commit()
    if not (ADMIN_USER and ADMIN_PASS):
        print("[!] Chưa đặt ADMIN_USER / ADMIN_PASS nên sẽ không có tài khoản admin.")


init()
app = FastAPI(title="SentinelJar", docs_url=None, redoc_url=None)
app.mount("/media", StaticFiles(directory=MUSIC_DIR), name="media")


# ---------- auth helpers ----------
def public(u) -> dict:
    return {"username": u["username"], "email": u["email"], "plan": u["plan"], "is_admin": bool(u["is_admin"])}


def token_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def current_user(request: Request):
    t = request.cookies.get(COOKIE)
    if not t:
        raise HTTPException(401, "Bạn chưa đăng nhập.")
    row = run(
        "SELECT u.* FROM sessions s JOIN users u ON u.username=s.username WHERE s.token=? AND s.created>?",
        (token_hash(t), time.time() - SESSION_DAYS * 86400),
        "one",
    )
    if not row:
        raise HTTPException(401, "Phiên đăng nhập đã hết hạn.")
    return row


def require_admin(user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Chỉ admin mới dùng được chức năng này.")
    return user


def start_session(response: Response, username: str):
    t = secrets.token_urlsafe(32)
    run("INSERT INTO sessions(token,username,created) VALUES(?,?,?)", (token_hash(t), username, time.time()))
    response.set_cookie(COOKIE, t, httponly=True, samesite="lax", max_age=SESSION_DAYS * 86400)


def verify_turnstile(token: str, ip: str):
    if not (TS_SITE and TS_SECRET):
        return
    if not token:
        raise HTTPException(400, "Hãy hoàn tất bước xác minh Cloudflare.")
    data = urllib.parse.urlencode({"secret": TS_SECRET, "response": token, "remoteip": ip}).encode()
    try:
        req = urllib.request.Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data)
        with urllib.request.urlopen(req, timeout=8) as r:
            ok = json.loads(r.read().decode()).get("success") is True
    except Exception:
        raise HTTPException(503, "Không liên hệ được Cloudflare để xác minh. Thử lại sau.")
    if not ok:
        raise HTTPException(400, "Xác minh Cloudflare không hợp lệ hoặc đã hết hạn. Thử lại.")


FAILS: dict = {}


def throttle(key: str):
    now = time.time()
    FAILS[key] = [t for t in FAILS.get(key, []) if now - t < 300]
    if len(FAILS[key]) >= 5:
        raise HTTPException(429, "Sai quá nhiều lần. Thử lại sau 5 phút.")


GATE_HOURS = 12
RATE: dict = {}


def rate_limit(key: str, n: int, window: int):
    now = time.time()
    RATE[key] = [t for t in RATE.get(key, []) if now - t < window]
    if len(RATE[key]) >= n:
        raise HTTPException(429, "Bạn thao tác quá nhanh. Thử lại sau ít phút.")
    RATE[key].append(now)


def gate_valid(request: Request) -> bool:
    if not (TS_SITE and TS_SECRET):
        return True
    t = request.cookies.get("sj_gate")
    return bool(t and run("SELECT 1 FROM gates WHERE token=? AND created>?", (token_hash(t), time.time() - GATE_HOURS * 3600), "one"))


def need_gate(request: Request):
    if not gate_valid(request):
        raise HTTPException(403, "GATE")


def hash_code(code: str, salt: str) -> str:
    return hashlib.sha256((salt + code).encode()).hexdigest()


def mask_email(e: str) -> str:
    name, _, dom = e.partition("@")
    return (name[:2] + "***" if len(name) > 2 else name[:1] + "***") + "@" + dom


def send_otp(to: str, code: str):
    if not SMTP_USER:
        print(f"[DEV] Mã OTP cho {to}: {code}   (chưa cấu hình SMTP nên chỉ hiện ở đây)")
        return
    msg = EmailMessage()
    msg["Subject"] = f"{code} là mã xác minh SentinelJar của bạn"
    msg["From"] = formataddr(("SentinelJar", SMTP_USER))
    msg["To"] = to
    msg.set_content(f"Mã xác minh SentinelJar của bạn là {code}. Mã có hiệu lực 10 phút. Nếu không phải bạn, hãy bỏ qua email này.")
    msg.add_alternative(
        f"""<div style="font-family:Arial,sans-serif;background:#0b0f1d;color:#e8ecf8;padding:28px;border-radius:14px;max-width:420px">
        <h2 style="margin:0 0 8px">SentinelJar 4.0</h2><p style="color:#8d97b5">Mã xác minh đăng ký của bạn:</p>
        <p style="font-size:34px;letter-spacing:8px;font-weight:700;color:#ff9d3c;margin:12px 0">{code}</p>
        <p style="color:#8d97b5;font-size:13px">Mã có hiệu lực 10 phút. Nếu không phải bạn đăng ký, hãy bỏ qua email này.</p></div>""",
        subtype="html",
    )
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as sv:
                sv.login(SMTP_USER, SMTP_PASS)
                sv.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as sv:
                sv.starttls()
                sv.login(SMTP_USER, SMTP_PASS)
                sv.send_message(msg)
    except Exception as e:
        print("[!] Gửi email lỗi:", e)
        raise HTTPException(503, "Không gửi được email xác minh. Thử lại sau.")


# ---------- models ----------
class RegisterIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,24}$")
    email: str = Field(pattern=r"^\S+@\S+\.\S+$", max_length=120)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(max_length=24)
    password: str = Field(max_length=128)


class EmailIn(BaseModel):
    email: str = Field(pattern=r"^\S+@\S+\.\S+$", max_length=120)


class VerifyIn(EmailIn):
    code: str = Field(pattern=r"^\d{6}$")


class GateIn(BaseModel):
    cf: str = Field(max_length=2048)


class KeyIn(BaseModel):
    code: str = Field(max_length=40)


class GenIn(BaseModel):
    plan: int = Field(ge=1, le=3)


# ---------- auth routes ----------
@app.get("/api/config")
def config(request: Request):
    on = bool(TS_SITE and TS_SECRET)
    return {"turnstile_site_key": TS_SITE if on else "", "gate_passed": gate_valid(request)}


@app.post("/api/gate")
def gate(body: GateIn, request: Request, response: Response):
    ip = request.client.host if request.client else ""
    rate_limit(f"gate|{ip}", 20, 600)
    verify_turnstile(body.cf, ip)
    t = secrets.token_urlsafe(32)
    run("INSERT INTO gates(token,created) VALUES(?,?)", (token_hash(t), time.time()))
    response.set_cookie("sj_gate", t, httponly=True, samesite="lax", max_age=GATE_HOURS * 3600)
    return {"ok": True}


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


@app.post("/api/register/start")
def register_start(body: RegisterIn, request: Request, _=Depends(need_gate)):
    ip = request.client.host if request.client else ""
    rate_limit(f"reg|{ip}", 6, 600)
    now = time.time()
    if run("SELECT 1 FROM users WHERE username=?", (body.username,), "one"):
        raise HTTPException(400, "Tên đăng nhập này đã có người dùng.")
    if run("SELECT 1 FROM users WHERE lower(email)=lower(?)", (body.email,), "one"):
        raise HTTPException(400, "Email này đã được dùng cho một tài khoản khác.")
    other = run("SELECT 1 FROM pending WHERE username=? AND lower(email)<>lower(?) AND expires>?", (body.username, body.email, now), "one")
    if other:
        raise HTTPException(400, "Tên này đang được người khác đăng ký. Hãy chọn tên khác.")
    old = run("SELECT last_sent FROM pending WHERE email=?", (body.email,), "one")
    if old and now - old["last_sent"] < 60:
        raise HTTPException(429, f"Chờ {int(60 - (now - old['last_sent']))} giây rồi thử lại.")
    salt, code = secrets.token_hex(16), new_code()
    run(
        "INSERT OR REPLACE INTO pending(email,username,salt,pw,code_hash,expires,tries,last_sent) VALUES(?,?,?,?,?,?,0,?)",
        (body.email, body.username, salt, hash_pw(body.password, salt), hash_code(code, salt), now + OTP_TTL, now),
    )
    try:
        send_otp(body.email, code)
    except HTTPException:
        run("DELETE FROM pending WHERE email=?", (body.email,))
        raise
    return {"email": mask_email(body.email)}


@app.post("/api/register/resend")
def register_resend(body: EmailIn, request: Request, _=Depends(need_gate)):
    ip = request.client.host if request.client else ""
    rate_limit(f"resend|{ip}", 6, 600)
    now = time.time()
    p = run("SELECT * FROM pending WHERE email=?", (body.email,), "one")
    if not p:
        raise HTTPException(400, "Không có đăng ký nào đang chờ. Hãy đăng ký lại.")
    if now - p["last_sent"] < 60:
        raise HTTPException(429, f"Chờ {int(60 - (now - p['last_sent']))} giây rồi thử lại.")
    code = new_code()
    run("UPDATE pending SET code_hash=?, expires=?, tries=0, last_sent=? WHERE email=?",
        (hash_code(code, p["salt"]), now + OTP_TTL, now, body.email))
    send_otp(body.email, code)
    return {"ok": True}


@app.post("/api/register/verify")
def register_verify(body: VerifyIn, response: Response, _=Depends(need_gate)):
    p = run("SELECT * FROM pending WHERE email=?", (body.email,), "one")
    if not p or p["expires"] < time.time():
        raise HTTPException(400, "Mã đã hết hạn. Hãy đăng ký lại.")
    if p["tries"] >= 5:
        run("DELETE FROM pending WHERE email=?", (body.email,))
        raise HTTPException(400, "Nhập sai quá nhiều lần. Hãy đăng ký lại.")
    if not secrets.compare_digest(p["code_hash"], hash_code(body.code, p["salt"])):
        run("UPDATE pending SET tries=tries+1 WHERE email=?", (body.email,))
        raise HTTPException(400, "Mã chưa đúng. Kiểm tra lại email của bạn.")
    try:
        run("INSERT INTO users(username,email,salt,pw,plan,is_admin) VALUES(?,?,?,?,0,0)",
            (p["username"], p["email"], p["salt"], p["pw"]))
    except sqlite3.IntegrityError:
        raise HTTPException(400, "Tên đăng nhập này vừa có người dùng. Hãy đăng ký lại.")
    run("DELETE FROM pending WHERE email=?", (body.email,))
    start_session(response, p["username"])
    return public(run("SELECT * FROM users WHERE username=?", (p["username"],), "one"))


@app.post("/api/login")
def login(body: LoginIn, request: Request, response: Response, _=Depends(need_gate)):
    key = f"{request.client.host if request.client else '?'}|{body.username.lower()}"
    throttle(key)
    u = run("SELECT * FROM users WHERE username=?", (body.username,), "one")
    ok = u and secrets.compare_digest(u["pw"], hash_pw(body.password, u["salt"]))
    if not ok:
        FAILS.setdefault(key, []).append(time.time())
        raise HTTPException(400, "Sai tên đăng nhập hoặc mật khẩu.")
    FAILS.pop(key, None)
    start_session(response, u["username"])
    return public(u)


@app.post("/api/logout")
def logout(request: Request, response: Response):
    t = request.cookies.get(COOKIE)
    if t:
        run("DELETE FROM sessions WHERE token=?", (token_hash(t),))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return public(user)


# ---------- license keys ----------
@app.post("/api/key/activate")
def activate(body: KeyIn, user=Depends(current_user)):
    code = body.code.strip().upper()
    with closing(conn()) as c:
        k = c.execute("SELECT plan, used_by FROM keys WHERE code=?", (code,)).fetchone()
        if not k:
            raise HTTPException(400, "Key không đúng. Kiểm tra lại hoặc hỏi admin.")
        if c.execute("UPDATE keys SET used_by=? WHERE code=? AND used_by IS NULL", (user["username"], code)).rowcount == 0:
            raise HTTPException(400, "Key này đã được dùng.")
        c.execute("UPDATE users SET plan=MAX(plan,?) WHERE username=?", (k["plan"], user["username"]))
        c.commit()
    return public(run("SELECT * FROM users WHERE username=?", (user["username"],), "one"))


@app.get("/api/admin/keys")
def list_keys(_=Depends(require_admin)):
    rows = run("SELECT code, plan, used_by FROM keys ORDER BY created DESC", fetch="all")
    return [dict(r) for r in rows]


@app.post("/api/admin/keys")
def make_key(body: GenIn, _=Depends(require_admin)):
    code = f"SJ-{PLAN_NAMES[body.plan]}-{secrets.token_hex(4).upper()}"
    run("INSERT INTO keys(code,plan,created) VALUES(?,?,?)", (code, body.plan, time.time()))
    return {"code": code, "plan": body.plan}


@app.get("/api/admin/users")
def list_users(_=Depends(require_admin)):
    rows = run("SELECT username,email,plan,is_admin FROM users ORDER BY rowid", fetch="all")
    return [{**dict(r), "is_admin": bool(r["is_admin"])} for r in rows]


# ---------- music ----------
@app.get("/api/music")
def list_music(_=Depends(current_user)):
    rows = run("SELECT id,title,filename FROM music ORDER BY id", fetch="all")
    return [{"id": r["id"], "title": r["title"], "url": f"/media/{r['filename']}"} for r in rows]


@app.post("/api/admin/music")
async def upload_music(file: UploadFile = File(...), _=Depends(require_admin)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, "Chỉ nhận file mp3, ogg, wav hoặc m4a.")
    name = uuid.uuid4().hex + ext
    dest = MUSIC_DIR / name
    size = 0
    try:
        with open(dest, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_MUSIC:
                    raise HTTPException(413, "File quá lớn (tối đa 30 MB).")
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    title = re.sub(r"[^\w .\-()]", "", Path(file.filename).stem)[:80].strip() or "Bài hát"
    run("INSERT INTO music(title,filename) VALUES(?,?)", (title, name))
    return {"ok": True, "title": title}


@app.delete("/api/admin/music/{mid}")
def delete_music(mid: int, _=Depends(require_admin)):
    r = run("SELECT filename FROM music WHERE id=?", (mid,), "one")
    if not r:
        raise HTTPException(404, "Không tìm thấy bài này.")
    (MUSIC_DIR / r["filename"]).unlink(missing_ok=True)
    run("DELETE FROM music WHERE id=?", (mid,))
    return {"ok": True}


# ---------- giao diện ----------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
from jar_viewer import make_router
app.include_router(make_router(current_user, rate_limit))
