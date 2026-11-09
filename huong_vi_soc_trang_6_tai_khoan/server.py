#!/usr/bin/env python3
"""Local member-managed website. Uses only Python standard library."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
import sqlite3, hashlib, secrets, json, os, time, hmac, threading, mimetypes, re
from http.cookies import SimpleCookie
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DB = ROOT / "website_data.sqlite3"
HOST = "0.0.0.0"
PORT = 8000
ITERATIONS = 310_000
sessions = {}
session_lock = threading.Lock()

def connect():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA busy_timeout=30000")
    return con

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()

def initialize():
    first_run = not DB.exists()
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY, display_name TEXT NOT NULL,
            salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS posts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL, image_data TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        columns = [row["name"] for row in con.execute("PRAGMA table_info(posts)").fetchall()]
        if "image_data" not in columns:
            con.execute("ALTER TABLE posts ADD COLUMN image_data TEXT NOT NULL DEFAULT ''")
        if first_run:
            seed_path = ROOT / "accounts_seed.json"
            if not seed_path.exists():
                raise RuntimeError("Thiếu accounts_seed.json. Hãy giải nén lại đầy đủ bộ cài.")
            accounts = json.loads(seed_path.read_text(encoding="utf-8"))
            for account in accounts:
                salt, digest = hash_password(account["password"])
                con.execute("INSERT INTO users VALUES(?,?,?,?,?)",
                    (account["username"], account["display_name"], salt, digest,
                     datetime.now().strftime("%d/%m/%Y %H:%M")))
            seed_path.unlink(missing_ok=True)
            print("Đã khởi tạo 6 tài khoản từ tệp tài khoản đi kèm.")

def now_text():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def re_image_data(value):
    if len(value) > 7_000_000:
        return False
    return bool(re.fullmatch(r"data:image/(?:jpeg|png|webp|gif);base64,[A-Za-z0-9+/]+={0,2}", value))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, status, payload, cookie=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 8_000_000:
                raise ValueError()
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            raise ValueError("Dữ liệu gửi lên không hợp lệ.")

    def session_user(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get("Cookie", ""))
        except Exception: return None
        morsel = cookie.get("sid")
        if not morsel: return None
        sid = morsel.value
        with session_lock:
            item = sessions.get(sid)
            if not item or item["expires"] < time.time():
                sessions.pop(sid, None)
                return None
            item["expires"] = time.time() + 8 * 60 * 60
            return item["username"]

    def require_user(self):
        username = self.session_user()
        if not username:
            self.send_json(401, {"error": "Bạn cần đăng nhập bằng một trong 6 tài khoản."})
            return None
        return username

    def do_GET(self):
        path = urlparse(self.path).path
        # Never expose account credentials, the SQLite database, or the seed file as static downloads.
        private_files = {
            "/TAI_KHOAN_6_THANH_VIEN.txt", "/THONG_TIN_TAI_KHOAN.txt",
            "/accounts_seed.json", "/website_data.sqlite3", "/server.py",
            "/BAT_DAU_WEBSITE.bat", "/MO_WEBSITE_VA_CLOUDFLARE.bat",
            "/CHAY_WEBSITE_AN.vbs", "/HUONG_DAN.txt"
        }
        if path in private_files or path.endswith(("-wal", "-shm")):
            return self.send_json(404, {"error": "Không tìm thấy tài nguyên."})
        if path == "/api/me":
            username = self.session_user()
            if not username:
                return self.send_json(200, {"user": None})
            with connect() as con:
                row = con.execute("SELECT username,display_name FROM users WHERE username=?", (username,)).fetchone()
            return self.send_json(200, {"user": dict(row) if row else None})
        if path == "/api/posts":
            with connect() as con:
                rows = con.execute("SELECT id,title,body,image_data,author,created_at FROM posts ORDER BY id DESC").fetchall()
            return self.send_json(200, {"posts": [dict(r) for r in rows]})
        if path == "/":
            self.path = "/website.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.body_json()
        except ValueError as e:
            return self.send_json(400, {"error": str(e)})
        if path == "/api/login":
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))
            with connect() as con:
                row = con.execute("SELECT username,display_name,salt,password_hash FROM users WHERE username=?", (username,)).fetchone()
            if not row:
                return self.send_json(401, {"error": "Tên tài khoản hoặc mật khẩu không đúng."})
            _, digest = hash_password(password, bytes.fromhex(row["salt"]))
            if not hmac.compare_digest(digest, row["password_hash"]):
                return self.send_json(401, {"error": "Tên tài khoản hoặc mật khẩu không đúng."})
            sid = secrets.token_urlsafe(32)
            with session_lock:
                sessions[sid] = {"username": username, "expires": time.time() + 8 * 60 * 60}
            cookie = f"sid={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
            return self.send_json(200, {"user": {"username": username, "display_name": row["display_name"]}}, cookie)
        if path == "/api/logout":
            cookie = SimpleCookie()
            try: cookie.load(self.headers.get("Cookie", ""))
            except Exception: pass
            morsel = cookie.get("sid")
            if morsel:
                with session_lock: sessions.pop(morsel.value, None)
            return self.send_json(200, {"ok": True}, "sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if path == "/api/change-password":
            username = self.require_user()
            if not username: return
            old = str(data.get("old_password", ""))
            new = str(data.get("new_password", ""))
            if len(new) < 10:
                return self.send_json(400, {"error": "Mật khẩu mới phải có ít nhất 10 ký tự."})
            with connect() as con:
                row = con.execute("SELECT salt,password_hash FROM users WHERE username=?", (username,)).fetchone()
                _, digest = hash_password(old, bytes.fromhex(row["salt"]))
                if not hmac.compare_digest(digest, row["password_hash"]):
                    return self.send_json(400, {"error": "Mật khẩu hiện tại không đúng."})
                salt, digest = hash_password(new)
                con.execute("UPDATE users SET salt=?,password_hash=? WHERE username=?", (salt,digest,username))
            return self.send_json(200, {"ok": True})
        if path == "/api/posts":
            username = self.require_user()
            if not username: return
            title, body = str(data.get("title", "")).strip(), str(data.get("body", "")).strip()
            image_data = str(data.get("image_data", ""))
            if image_data and not re_image_data(image_data):
                return self.send_json(400, {"error": "Ảnh không hợp lệ. Chỉ hỗ trợ JPG, PNG, WEBP hoặc GIF; tối đa 5 MB."})
            if not title or not body or len(title) > 120 or len(body) > 10000:
                return self.send_json(400, {"error": "Tiêu đề/nội dung không hợp lệ hoặc vượt giới hạn."})
            with connect() as con:
                row = con.execute("SELECT display_name FROM users WHERE username=?", (username,)).fetchone()
                stamp = now_text()
                cur = con.execute("INSERT INTO posts(title,body,image_data,author,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (title,body,image_data,row["display_name"],stamp,stamp))
                post_id = cur.lastrowid
            return self.send_json(201, {"ok": True, "id": post_id})
        return self.send_json(404, {"error": "Không tìm thấy chức năng."})

    def do_PUT(self):
        path = urlparse(self.path).path
        username = self.require_user()
        if not username: return
        try: data = self.body_json()
        except ValueError as e: return self.send_json(400, {"error": str(e)})
        try: post_id = int(path.rsplit("/",1)[1])
        except Exception: return self.send_json(404, {"error": "Không tìm thấy bài viết."})
        title, body = str(data.get("title","")).strip(), str(data.get("body","")).strip()
        image_data = data.get("image_data", None)
        if image_data is not None:
            image_data = str(image_data)
            if image_data and not re_image_data(image_data):
                return self.send_json(400, {"error": "Ảnh không hợp lệ. Chỉ hỗ trợ JPG, PNG, WEBP hoặc GIF; tối đa 5 MB."})
        if not title or not body or len(title)>120 or len(body)>10000:
            return self.send_json(400, {"error": "Tiêu đề/nội dung không hợp lệ hoặc vượt giới hạn."})
        with connect() as con:
            if image_data is None:
                cur = con.execute("UPDATE posts SET title=?,body=?,updated_at=? WHERE id=?",
                    (title,body,now_text(),post_id))
            else:
                cur = con.execute("UPDATE posts SET title=?,body=?,image_data=?,updated_at=? WHERE id=?",
                    (title,body,image_data,now_text(),post_id))
            if not cur.rowcount: return self.send_json(404, {"error": "Bài viết không tồn tại."})
        return self.send_json(200, {"ok": True})

    def do_DELETE(self):
        path = urlparse(self.path).path
        username = self.require_user()
        if not username: return
        try: post_id = int(path.rsplit("/",1)[1])
        except Exception: return self.send_json(404, {"error": "Không tìm thấy bài viết."})
        with connect() as con:
            cur = con.execute("DELETE FROM posts WHERE id=?", (post_id,))
            if not cur.rowcount: return self.send_json(404, {"error": "Bài viết không tồn tại."})
        return self.send_json(200, {"ok": True})

if __name__ == "__main__":
    initialize()
    print(f"Website đang chạy tại http://127.0.0.1:{PORT}")
    print(f"Co so du lieu dung chung: {DB}")
    print("Cac thanh vien truy cap cung may chu nay de dung chung bai viet.")
    print("Giu cua so nay mo khi su dung. Nhan Ctrl+C de dung.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
