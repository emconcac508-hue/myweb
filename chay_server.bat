@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === SentinelJar 4.0 ===
pip install -r requirements.txt
set ADMIN_USER=admin
set ADMIN_PASS=18122012
REM Bo REM o 2 dong duoi de bat xac minh Cloudflare (lay khoa tai dash.cloudflare.com ^> Turnstile)
REM set TURNSTILE_SITE_KEY=
REM set TURNSTILE_SECRET=
REM Bo REM o 2 dong duoi de gui OTP qua Gmail (dung Mat khau ung dung 16 ky tu)
set SMTP_USER=khangleduykhang67@gmail.com
set SMTP_PASS=sjik chwk nqrd dkwa
python -m uvicorn server:app --host 127.0.0.1 --port 8000
pause
