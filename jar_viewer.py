"""jar_viewer.py - API decompile cho SentinelJar (chỉ gói PRO trở lên).

Cần: Java + cfr.jar (https://github.com/leibnitz27/cfr/releases) đặt ở tools/cfr.jar
(hoặc đặt biến môi trường CFR_JAR). Việc xem cây file / bytecode / chuỗi chạy ngay trên
trình duyệt, server chỉ nhận 1 file .class khi người dùng bấm Decompile.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

BASE = Path(__file__).resolve().parent
CFR_JAR = Path(os.environ.get("CFR_JAR", BASE / "tools" / "cfr.jar"))
MIN_PLAN = 2  # 1 BASIC, 2 PRO, 3 ELITE
MAX_CLASS = 3 * 1024 * 1024
NAME_OK = re.compile(r"^[\w$.-]{1,150}\.class$")


def _cfr(files: dict, main: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            (Path(tmp) / name).write_bytes(data)
        try:
            r = subprocess.run(
                ["java", "-jar", str(CFR_JAR), str(Path(tmp) / main), "--extraclasspath", tmp],
                capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
            )
        except FileNotFoundError:
            raise HTTPException(503, "Server chưa cài Java nên chưa decompile được.")
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "Decompile quá lâu, file này quá phức tạp.")
        if not r.stdout.strip():
            err = (r.stderr or "").replace(tmp, "").strip().splitlines()
            raise HTTPException(500, "Không decompile được file này." + (f" ({err[-1][:160]})" if err else ""))
        return r.stdout


def make_router(current_user, rate_limit) -> APIRouter:
    router = APIRouter()

    @router.get("/jar-viewer.js")
    def client_js():
        return FileResponse(BASE / "jar-viewer.js", media_type="text/javascript")

    @router.post("/api/decompile")
    async def decompile(files: List[UploadFile] = File(...), user=Depends(current_user)):
        # Kiểm tra gói ở server, không chỉ ẩn nút ở giao diện
        if not user["is_admin"] and user["plan"] < MIN_PLAN:
            raise HTTPException(403, "Decompile chỉ dành cho gói PRO trở lên.")
        rate_limit(f"dec|{user['username']}", 30, 300)
        if not CFR_JAR.exists():
            raise HTTPException(503, "Server chưa có tools/cfr.jar.")
        if not files or len(files) > 60:
            raise HTTPException(400, "Số file class không hợp lệ.")
        blobs, total = {}, 0
        for f in files:
            name = os.path.basename(f.filename or "")
            if not NAME_OK.match(name):
                raise HTTPException(400, "Tên file class không hợp lệ.")
            data = await f.read(MAX_CLASS + 1)
            total += len(data)
            if len(data) > MAX_CLASS or total > 4 * MAX_CLASS:
                raise HTTPException(413, "File class quá lớn.")
            if data[:4] != b"\xca\xfe\xba\xbe":
                raise HTTPException(400, "Đây không phải file .class.")
            blobs[name] = data
        main = os.path.basename(files[0].filename)
        return {"text": await run_in_threadpool(_cfr, blobs, main)}

    return router
