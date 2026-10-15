"""Pruebas de la migración — que arrancar sobre una base vieja no pierda nada.

## Qué cambió respecto a la versión anterior, y por qué

La versión anterior **copiaba `platform.db`, la base real del CEO**, desde una
ruta absoluta de Windows y la migraba. Tres problemas, cada uno suficiente:

1. **Reventaba fuera de este equipo.** `C:\\Aura\\...` y una carpeta temporal de
   una sesión que ya no existe: en Linux, y en esta misma máquina después de
   limpiar el temporal, la suite fallaba antes de la primera comprobación. Por
   eso el paso de pruebas se había retirado del flujo de publicación.
2. **No imprimía la línea `RESULTADO:`**, así que `run_all.py` no podía sumar
   sus comprobaciones y el total del proyecto las ignoraba en silencio.
3. **Apuntaba a los datos reales.** Copiaba antes de tocar nada, sí, pero una
   prueba automática que abre la base de producción es una prueba a un error
   de tecleo de distancia del desastre.

Ahora **se fabrica una base vieja desde cero**: el esquema tal como estaba
antes de E1, con filas dentro. Es más honesto como prueba —el estado inicial
es explícito y reproducible, no «lo que hubiera ese día en la base del CEO»— y
corre en cualquier máquina.

**El ensayo contra la base real sigue existiendo**, donde debe estar: como una
acción deliberada que una persona lanza a mano antes de arrancar en real.

    cd platform && python -m app.migrate --simular
"""
import os
import pathlib
import sqlite3
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="aura_migrate_")
DB = os.path.join(TMP, "vieja.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["EXPORT_DIR"] = os.path.join(TMP, "exports")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


# --- El esquema de ANTES de E1, copiado del que tiene hoy la base real -------
#
# Sin `is_active`, sin `failed_login_count`, sin `locked_until`, sin
# `last_login_at`, sin `account_id`, y sin las tablas `login_attempts` ni
# `audit_log`. Es el punto de partida que la migración tiene que resolver.

ESQUEMA_VIEJO = """
CREATE TABLE users (
    id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    phone VARCHAR,
    password_hash VARCHAR NOT NULL,
    role VARCHAR(6) NOT NULL,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY (id)
);
CREATE TABLE properties (
    id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    title VARCHAR NOT NULL,
    zone VARCHAR,
    city VARCHAR,
    price_amount NUMERIC(12, 2),
    price_currency VARCHAR,
    status VARCHAR(9),
    bedrooms INTEGER,
    bathrooms NUMERIC(3, 1),
    area_m2 NUMERIC(8, 2),
    description TEXT,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY (id),
    FOREIGN KEY(owner_id) REFERENCES users (id)
);
"""

HASH = "$2b$12$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTU"

con = sqlite3.connect(DB)
con.executescript(ESQUEMA_VIEJO)
con.executemany(
    "INSERT INTO users (id, name, email, password_hash, role) VALUES (?,?,?,?,?)",
    [(1, "Administradora", "admin@aura-homes-cancun.local", HASH, "admin"),
     (2, "Propietaria Uno", "uno@test.local", HASH, "owner"),
     (3, "Propietario Dos", "dos@test.local", HASH, "owner")],
)
con.executemany(
    "INSERT INTO properties (id, owner_id, title) VALUES (?,?,?)",
    [(1, 2, "Casa A"), (2, 2, "Casa B"), (3, 3, "Casa C")],
)
con.commit()
con.close()


def retrato(ruta):
    """Lo que la migración NO puede tocar: las filas que ya existían."""
    c = sqlite3.connect(ruta)
    users = c.execute("SELECT id, name, email, role FROM users ORDER BY id").fetchall()
    props = c.execute("SELECT id, title, owner_id FROM properties ORDER BY id").fetchall()
    c.close()
    return users, props


def columnas(ruta, tabla):
    c = sqlite3.connect(ruta)
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({tabla})")]
    c.close()
    return cols


def tablas(ruta):
    c = sqlite3.connect(ruta)
    ts = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    c.close()
    return ts


antes_u, antes_p = retrato(DB)
print(f"Base de prueba: {DB}")
print(f"ANTES: {len(antes_u)} usuarios, {len(antes_p)} propiedades, "
      f"{len(tablas(DB))} tablas\n")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

print("== 1. Arranque sobre la base vieja ==")
with TestClient(app) as c:
    check("la aplicación arranca y responde", c.get("/api/health").status_code == 200)

despues_u, despues_p = retrato(DB)
print(f"\nDESPUES: {len(despues_u)} usuarios, {len(despues_p)} propiedades, "
      f"{len(tablas(DB))} tablas\n")

print("== 2. Los datos que ya existían siguen ahí, iguales ==")
check("ningún usuario cambió ni desapareció", antes_u == despues_u,
      f"-> {antes_u} != {despues_u}")
check("ninguna propiedad cambió ni desapareció", antes_p == despues_p,
      f"-> {antes_p} != {despues_p}")

print("\n== 3. Columnas que la migración tenía que añadir ==")
cols_users = columnas(DB, "users")
for col in ("is_active", "failed_login_count", "locked_until", "last_login_at",
            "account_id", "password_changed_at"):
    check(f"users.{col}", col in cols_users)
cols_props = columnas(DB, "properties")
for col in ("site_ref", "account_id", "tax_jurisdiction"):
    check(f"properties.{col}", col in cols_props)

print("\n== 4. Tablas que la migración tenía que crear ==")
ts = tablas(DB)
for t in ("login_attempts", "audit_log", "accounts", "account_plan_events",
          "password_reset_tokens", "providers", "expenses", "fx_rates",
          "fiscal_year_closures", "ticket_quotes", "fiscal_exports"):
    check(f"tabla {t}", t in ts)

print("\n== 5. Relleno de cuentas: nadie se queda sin cuenta ==")
con = sqlite3.connect(DB)
sin_cuenta_u = con.execute("SELECT COUNT(*) FROM users WHERE account_id IS NULL").fetchone()[0]
sin_cuenta_p = con.execute("SELECT COUNT(*) FROM properties WHERE account_id IS NULL").fetchone()[0]
n_cuentas = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
# Cada propiedad tiene que acabar en la cuenta de su dueño: si no, el
# aislamiento por cuenta enseñaría la casa de un cliente a otro.
cruzadas = con.execute(
    "SELECT COUNT(*) FROM properties p JOIN users u ON u.id = p.owner_id "
    "WHERE p.account_id IS NOT NULL AND u.account_id IS NOT NULL "
    "AND p.account_id != u.account_id").fetchone()[0]
con.close()
check("ningún usuario sin cuenta", sin_cuenta_u == 0, f"-> {sin_cuenta_u}")
check("ninguna propiedad sin cuenta", sin_cuenta_p == 0, f"-> {sin_cuenta_p}")
check("se crearon cuentas", n_cuentas >= 1, f"-> {n_cuentas}")
check("ninguna casa quedó en una cuenta distinta a la de su dueño", cruzadas == 0,
      f"-> {cruzadas}")

print("\n== 6. Arrancar otra vez no vuelve a migrar ni duplica nada ==")
with TestClient(app) as c:
    check("la aplicación arranca de nuevo", c.get("/api/health").status_code == 200)
otra_u, otra_p = retrato(DB)
con = sqlite3.connect(DB)
n_cuentas_2 = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
con.close()
check("los usuarios siguen idénticos", antes_u == otra_u)
check("las propiedades siguen idénticas", antes_p == otra_p)
check("no se duplicaron las cuentas", n_cuentas_2 == n_cuentas,
      f"-> {n_cuentas} luego {n_cuentas_2}")

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
