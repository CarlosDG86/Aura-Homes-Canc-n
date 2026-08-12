import os, sys, shutil, pathlib, sqlite3
import pathlib
REAL = r"C:\Aura\claude-code\platform\data\platform.db"
COPY = r"C:\Users\carlo\AppData\Local\Temp\claude\C--Aura-claude-code\4c0c4031-2c33-449a-9ee9-06b5fad4d598\scratchpad\real_copy.db"
shutil.copy(REAL, COPY)

def snap(db):
    c = sqlite3.connect(db)
    users = c.execute("SELECT id,name,email,role FROM users ORDER BY id").fetchall()
    props = c.execute("SELECT id,title,owner_id FROM properties ORDER BY id").fetchall()
    c.close(); return users, props

before_u, before_p = snap(COPY)
print(f"ANTES: {len(before_u)} usuarios, {len(before_p)} propiedades")

os.environ["DATABASE_URL"] = f"sqlite:///{COPY}"
os.environ["APP_ENV"] = "dev"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    assert c.get("/api/health").status_code == 200

after_u, after_p = snap(COPY)
print(f"DESPUES: {len(after_u)} usuarios, {len(after_p)} propiedades")
conn = sqlite3.connect(COPY)
cols = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
conn.close()

ok = True
for col in ["is_active","failed_login_count","locked_until","last_login_at"]:
    good = col in cols; ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  columna users.{col}")
for t in ["login_attempts","audit_log"]:
    good = t in tables; ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  tabla {t}")
same = (before_u == after_u and before_p == after_p)
ok &= same
print(f"  {'PASS' if same else 'FAIL'}  datos reales intactos (usuarios y propiedades idénticos)")
sys.exit(0 if ok else 1)
