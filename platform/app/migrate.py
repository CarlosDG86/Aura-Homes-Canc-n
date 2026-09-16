"""Migración de la etapa E9: cuentas como raíz de aislamiento (D-013).

No hay Alembic en este proyecto. El esquema se aplica al arrancar, con
`create_all()` para las tablas nuevas y funciones idempotentes que hacen
`PRAGMA table_info` + `ALTER TABLE ADD COLUMN` para las columnas. Este módulo
sigue ese patrón y añade lo único que el resto no hace: **escribir filas**.

## Dónde se llama, y por qué importa tanto

`migrar()` se invoca desde `main.py`, en el `on_startup`, **justo después de
las tres `_ensure_*` y antes del bloque de siembra**. No es una preferencia de
estilo: el bloque de siembra hace `if existing_admin: return` y sale de
`on_startup()`. La base real del CEO tiene un administrador, así que cualquier
cosa registrada después de esa línea **nunca correría allí** — y, peor, sí
correría sobre una base nueva y vacía, así que las pruebas locales pasarían y
solo la base del CEO quedaría sin migrar.

## Qué hace el relleno, en una sola transacción

1. Crea la cuenta operadora de Aura y le asigna todos los administradores.
2. Crea una cuenta por cada propietario que no tenga.
3. Marca como **operadora** toda cuenta con alguna propiedad publicada en el
   sitio (`site_ref IS NOT NULL`). Sin esto, la siguiente sincronización
   dejaría de publicar las casas que ya están en el sitio.
4. Copia la cuenta del dueño a cada propiedad.
5. Asigna a cada inquilino la cuenta del dueño de su arrendamiento activo. Si
   hay cero o más de un candidato, lo deja en NULL y lo reporta.

Las cuentas migradas nacen con `plan_assigned_at = NULL` («plan sin asignar»)
y sin reloj de prueba: nadie hereda una prueba ya empezada, y ninguna queda
por encima de su límite el primer día (D-020).
"""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import text

from . import plans

#: Versión de esquema que deja esta migración. Sin esto, una base a medio
#: migrar y una recién creada son indistinguibles.
SCHEMA_VERSION = "C1"
SCHEMA_VERSION_KEY = "schema_version"

#: Nombre de la cuenta operadora. `docs/decisions/DECISION_LOG.md` D-011 sigue
#: abierta (¿«Enterprise» o «Business» Solutions?); se usa el que hoy aparece
#: en CLAUDE.md y se renombra con un UPDATE cuando el CEO decida.
CUENTA_OPERADORA = "Aura Enterprise Solutions"


# --- DDL ---------------------------------------------------------------------


def _ensure_account_columns(engine) -> None:
    """`properties.account_id`. (`users.account_id` la añade `main.py`.)"""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(properties)"))}
        if not cols:
            return  # la tabla no existe todavía; create_all se encarga
        if "account_id" not in cols:
            conn.execute(text("ALTER TABLE properties ADD COLUMN account_id INTEGER"))


def _ensure_login_attempt_kind(engine) -> None:
    """`login_attempts.kind` (E10).

    Va acompañada **en el mismo commit** del filtro `kind IS NULL` en
    `security.ip_is_rate_limited`. Sin esa línea, las solicitudes de
    recuperación cuentan como fallos de acceso y once peticiones a
    `/recuperar` dejan sin `/login` a toda una IP compartida durante un
    minuto: una negación de servicio trivial contra una oficina.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(login_attempts)"))}
        if not cols:
            return
        if "kind" not in cols:
            conn.execute(text("ALTER TABLE login_attempts ADD COLUMN kind VARCHAR"))


def _ensure_missing_indexes(engine) -> None:
    """Índices nuevos y deuda acumulada, todos con `IF NOT EXISTS`.

    Va después del DDL de columnas porque `ix_properties_account_id` depende de
    una columna que acaba de añadirse.

    Los índices UNIQUE se crean solo si los datos ya cumplen la restricción.
    En la base real, `properties.site_ref` **no tiene** el índice único que
    `models.py` declara, así que hoy nada impide dos propiedades apuntando a la
    misma ficha pública. Crearlo a ciegas sobre datos duplicados reventaría el
    arranque; comprobarlo antes convierte un fallo de arranque en un aviso.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    normales = {
        "ix_properties_account_id": "CREATE INDEX IF NOT EXISTS ix_properties_account_id ON properties (account_id)",
        "ix_users_account_id": "CREATE INDEX IF NOT EXISTS ix_users_account_id ON users (account_id)",
        "ix_leases_property_status": "CREATE INDEX IF NOT EXISTS ix_leases_property_status ON leases (property_id, status)",
        "ix_leases_tenant_status": "CREATE INDEX IF NOT EXISTS ix_leases_tenant_status ON leases (tenant_id, status)",
        "ix_maintenance_tickets_property_id": "CREATE INDEX IF NOT EXISTS ix_maintenance_tickets_property_id ON maintenance_tickets (property_id)",
    }
    unicos = {
        "ix_properties_site_ref": ("properties", "site_ref"),
        "ix_maintenance_tickets_public_ref": ("maintenance_tickets", "public_ref"),
    }

    with engine.begin() as conn:
        existentes = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))}

        for nombre, ddl in normales.items():
            tabla = ddl.split(" ON ")[1].split(" ")[0]
            if tabla in existentes:
                try:
                    conn.execute(text(ddl))
                except Exception as exc:  # noqa: BLE001
                    print(f"  [migración] no se pudo crear {nombre}: {exc}")

        for nombre, (tabla, col) in unicos.items():
            if tabla not in existentes:
                continue
            cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({tabla})"))}
            if col not in cols:
                continue
            fila = conn.execute(text(
                f"SELECT COUNT({col}), COUNT(DISTINCT {col}) FROM {tabla}")).fetchone()
            if fila and fila[0] != fila[1]:
                print(f"  [migración] AVISO: {tabla}.{col} tiene valores repetidos "
                      f"({fila[0]} filas, {fila[1]} distintos). No se crea {nombre}; "
                      f"hay que resolver los duplicados a mano.")
                continue
            try:
                conn.execute(text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {nombre} ON {tabla} ({col})"))
            except Exception as exc:  # noqa: BLE001
                print(f"  [migración] no se pudo crear {nombre}: {exc}")


# --- Versión de esquema ------------------------------------------------------


def _schema_version(db) -> Optional[str]:
    from .models import PlatformSetting

    fila = db.query(PlatformSetting).filter(
        PlatformSetting.key == SCHEMA_VERSION_KEY).first()
    return fila.value if fila else None


def _set_schema_version(db, valor: str) -> None:
    from .models import PlatformSetting

    fila = db.query(PlatformSetting).filter(
        PlatformSetting.key == SCHEMA_VERSION_KEY).first()
    if fila:
        fila.value = valor
    else:
        db.add(PlatformSetting(key=SCHEMA_VERSION_KEY, value=valor))


# --- Relleno de filas --------------------------------------------------------


def _nombre_base(engine) -> Optional[str]:
    ruta = engine.url.database
    return os.path.basename(ruta) if ruta else None


def _backfill_accounts(engine, SessionLocal) -> dict:
    """Crea las cuentas y reparte `account_id`. Idempotente.

    Todo en una transacción: si algo falla a media asignación, una propiedad
    podría quedar en una cuenta y su dueño en otra, que es exactamente la
    deriva que `PRAGMA foreign_keys = 0` no puede impedir.
    """
    from .models import Account, Lease, LeaseStatusEnum, Property, RoleEnum, User

    resumen = {"cuentas_creadas": 0, "usuarios_asignados": 0,
               "propiedades_asignadas": 0, "inquilinos_sin_cuenta": 0,
               "omitida": False}

    db = SessionLocal()
    try:
        if _schema_version(db) == SCHEMA_VERSION:
            resumen["omitida"] = True
            return resumen

        origen = _nombre_base(engine)

        # 1. Cuenta operadora de Aura, para los administradores.
        admins = db.query(User).filter(User.role == RoleEnum.admin).all()
        if admins:
            operadora = db.query(Account).filter(
                Account.name == CUENTA_OPERADORA).first()
            if operadora is None:
                operadora = Account(
                    name=CUENTA_OPERADORA, is_operator=True,
                    plan=plans.PLAN_ENTERPRISE_PLUS, status=plans.ESTADO_ACTIVA,
                    plan_assigned_at=None, trial_started_at=None,
                    created_in_db=origen,
                )
                db.add(operadora)
                db.flush()
                resumen["cuentas_creadas"] += 1
            for a in admins:
                if a.account_id is None:
                    a.account_id = operadora.id
                    resumen["usuarios_asignados"] += 1

        # 2. Una cuenta por propietario que no tenga.
        for duenio in db.query(User).filter(User.role == RoleEnum.owner,
                                            User.account_id.is_(None)).all():
            cuenta = Account(
                name=duenio.name or f"Propietario #{duenio.id}",
                plan=plans.PLAN_ENTERPRISE_PLUS,
                status=plans.ESTADO_ACTIVA,
                # «Plan sin asignar»: nadie ha decidido todavía su plan
                # comercial, y la ficha de administración lo pinta así.
                plan_assigned_at=None,
                # Nadie hereda un reloj de prueba ya empezado (D-020).
                trial_started_at=None, trial_ends_at=None,
                primary_user_id=duenio.id,
                created_in_db=origen,
            )
            db.add(cuenta)
            db.flush()
            duenio.account_id = cuenta.id
            resumen["cuentas_creadas"] += 1
            resumen["usuarios_asignados"] += 1

        # La sesión se abre con `autoflush=False` (db.py:45), así que las
        # asignaciones de arriba siguen pendientes y NO las ve ninguna
        # consulta. Sin este flush explícito, el paso 3 consultaba una foto
        # incompleta: solo veía a los propietarios cuya asignación había
        # volcado por casualidad el `flush()` de una iteración posterior, y el
        # último se quedaba fuera. En la base real eso dejaba una de las tres
        # casas publicadas en una cuenta no operadora, es decir, sin publicar
        # a la siguiente sincronización.
        db.flush()

        # 3. Operadora = tiene alguna propiedad publicada en el sitio.
        #    Sin esto, la sincronización dejaría de publicar las casas que ya
        #    están en el sitio público.
        cuentas_de_owner = [
            fila[0] for fila in db.query(User.account_id)
                                  .filter(User.role == RoleEnum.owner,
                                          User.account_id.isnot(None))
                                  .distinct().all()
        ]
        con_publicadas = {
            fila[0] for fila in db.query(User.account_id)
                                  .join(Property, Property.owner_id == User.id)
                                  .filter(User.account_id.isnot(None),
                                          Property.site_ref.isnot(None))
                                  .distinct().all()
        }
        for cuenta_id in cuentas_de_owner:
            if cuenta_id in con_publicadas:
                cuenta = db.get(Account, cuenta_id)
                if cuenta is not None and not cuenta.is_operator:
                    cuenta.is_operator = True

        # 4. Cada propiedad hereda la cuenta de su dueño.
        for prop in db.query(Property).filter(Property.account_id.is_(None)).all():
            duenio = db.get(User, prop.owner_id)
            if duenio is not None and duenio.account_id is not None:
                prop.account_id = duenio.account_id
                resumen["propiedades_asignadas"] += 1

        # Segundo flush obligatorio, por el mismo motivo que el anterior: el
        # paso 5 consulta `Property.account_id`, que el paso 4 acaba de dejar
        # pendiente. Sin esto, la consulta lee NULL y ningún inquilino recibe
        # cuenta.
        db.flush()

        # 5. Inquilinos: la cuenta del dueño de su arrendamiento activo.
        for inq in db.query(User).filter(User.role == RoleEnum.tenant,
                                         User.account_id.is_(None)).all():
            cuentas = {
                fila[0]
                for fila in db.query(Property.account_id)
                              .join(Lease, Lease.property_id == Property.id)
                              .filter(Lease.tenant_id == inq.id,
                                      Lease.status == LeaseStatusEnum.active,
                                      Property.account_id.isnot(None))
                              .distinct()
            }
            if len(cuentas) == 1:
                inq.account_id = cuentas.pop()
                resumen["usuarios_asignados"] += 1
            else:
                # Cero o varias: se deja NULL a propósito y se reporta. Adivinar
                # metería a una persona en la cuenta equivocada.
                resumen["inquilinos_sin_cuenta"] += 1

        _set_schema_version(db, SCHEMA_VERSION)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return resumen


def asegurar_cuenta_operadora(db, engine) -> Optional[int]:
    """Da cuenta operadora a los administradores que no tengan. Devuelve su id.

    Existe porque en una base **nueva** el orden juega en contra: `migrar()`
    corre antes que el bloque de siembra, así que cuando se rellenan las
    cuentas todavía no hay ningún administrador y el paso 1 no encuentra a
    quién asignar. Sin esta función, el administrador de una instalación
    recién creada se quedaría sin cuenta para siempre — y `migrar()` no lo
    arreglaría en el siguiente arranque, porque la versión de esquema ya
    estaría fijada y el relleno se salta.

    Idempotente: se puede llamar en cada arranque.
    """
    from .models import Account, RoleEnum, User

    admins = db.query(User).filter(User.role == RoleEnum.admin).all()
    if not admins:
        return None

    cuenta = db.query(Account).filter(Account.name == CUENTA_OPERADORA).first()
    if cuenta is None:
        cuenta = Account(
            name=CUENTA_OPERADORA, is_operator=True,
            plan=plans.PLAN_ENTERPRISE_PLUS, status=plans.ESTADO_ACTIVA,
            plan_assigned_at=None, trial_started_at=None,
            created_in_db=_nombre_base(engine),
        )
        db.add(cuenta)
        db.flush()

    cambios = False
    for a in admins:
        if a.account_id is None:
            a.account_id = cuenta.id
            cambios = True
    if cambios:
        db.commit()
    return cuenta.id


# --- Verificación ------------------------------------------------------------


def verificar_integridad_cuentas(SessionLocal, imprimir: bool = True) -> dict:
    """Busca deriva entre `properties.account_id` y la cuenta de su dueño.

    Solo lee. No corrige nada y no lanza: si el arranque se cayera por esto, un
    dato torcido dejaría la plataforma inaccesible en vez de avisando.

    Es lo único que detecta la deriva, porque `PRAGMA foreign_keys` devuelve 0
    en las dos bases y SQLite no impone ninguna de las claves declaradas.
    """
    from .models import Account, Property, RoleEnum, User

    db = SessionLocal()
    try:
        derivadas = (db.query(Property.id)
                     .join(User, User.id == Property.owner_id)
                     .filter(Property.account_id.isnot(None),
                             User.account_id.isnot(None),
                             Property.account_id != User.account_id)
                     .count())
        prop_sin_cuenta = db.query(Property).filter(Property.account_id.is_(None)).count()
        user_sin_cuenta = (db.query(User)
                           .filter(User.account_id.is_(None),
                                   User.role != RoleEnum.tenant)
                           .count())
        cuentas_huerfanas = 0
        for cuenta_id, in db.query(Account.id).all():
            tiene_props = db.query(Property.id).filter(
                Property.account_id == cuenta_id).first() is not None
            tiene_users = db.query(User.id).filter(
                User.account_id == cuenta_id).first() is not None
            if tiene_props and not tiene_users:
                cuentas_huerfanas += 1
    finally:
        db.close()

    hallazgos = {
        "propiedades_con_cuenta_derivada": derivadas,
        "propiedades_sin_cuenta": prop_sin_cuenta,
        "usuarios_sin_cuenta": user_sin_cuenta,
        "cuentas_con_propiedades_y_sin_usuarios": cuentas_huerfanas,
    }
    if imprimir and any(hallazgos.values()):
        print("=" * 72)
        print("AVISO DE INTEGRIDAD DE CUENTAS")
        for clave, valor in hallazgos.items():
            if valor:
                print(f"  {clave.replace('_', ' ')}: {valor}")
        print("  Nada se ha corregido automáticamente. Revisar antes de dar de")
        print("  alta clientes nuevos.")
        print("=" * 72)
    return hallazgos


# --- Punto de entrada --------------------------------------------------------


def migrar(engine, SessionLocal, verbose: bool = False) -> dict:
    """DDL + relleno + verificación. Idempotente: correrlo dos veces no cambia nada."""
    _ensure_account_columns(engine)
    _ensure_login_attempt_kind(engine)
    _ensure_missing_indexes(engine)
    resumen = _backfill_accounts(engine, SessionLocal)
    if verbose and not resumen["omitida"]:
        print(f"  [migración E9] cuentas creadas: {resumen['cuentas_creadas']}, "
              f"usuarios asignados: {resumen['usuarios_asignados']}, "
              f"propiedades asignadas: {resumen['propiedades_asignadas']}")
        if resumen["inquilinos_sin_cuenta"]:
            print(f"  [migración E9] inquilinos sin cuenta resoluble: "
                  f"{resumen['inquilinos_sin_cuenta']} (se dejaron en NULL)")
    resumen["integridad"] = verificar_integridad_cuentas(SessionLocal)
    return resumen


# --- Ensayo en seco ----------------------------------------------------------
#
# `python -m app.migrate --simular [ruta.db]`
#
# Obligatorio antes de arrancar contra la base real. Trabaja SIEMPRE sobre una
# copia; la original no se abre nunca en modo escritura.


def _radiografia(ruta: str) -> dict:
    """Tablas, columnas, índices y número de filas de una base."""
    import sqlite3

    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        tablas = sorted(r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"))
        foto = {"tablas": {}, "indices": sorted(
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%'"))}
        for t in tablas:
            cols = sorted(r[1] for r in con.execute(f"PRAGMA table_info({t})"))
            filas = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            foto["tablas"][t] = {"columnas": cols, "filas": filas}
        return foto
    finally:
        con.close()


def _diff(antes: dict, despues: dict) -> list[str]:
    lineas = []
    for t in sorted(set(despues["tablas"]) - set(antes["tablas"])):
        lineas.append(f"  + tabla {t}")
    for t in sorted(set(antes["tablas"]) & set(despues["tablas"])):
        nuevas = set(despues["tablas"][t]["columnas"]) - set(antes["tablas"][t]["columnas"])
        for c in sorted(nuevas):
            lineas.append(f"  + columna {t}.{c}")
        a, d = antes["tablas"][t]["filas"], despues["tablas"][t]["filas"]
        if a != d:
            lineas.append(f"  ~ filas {t}: {a} -> {d}")
    for i in sorted(set(despues["indices"]) - set(antes["indices"])):
        lineas.append(f"  + índice {i}")
    return lineas


def _simular(origen: str) -> int:
    import shutil
    import sys
    import tempfile

    from .backup import _snapshot

    if not os.path.exists(origen):
        print(f"ERROR: no existe {origen}")
        return 1

    tmp = tempfile.mkdtemp(prefix="aura_simular_")
    copia = os.path.join(tmp, "copia.db")
    info = _snapshot(origen, copia)
    print(f"Copia verificada de {origen}")
    print(f"  -> {copia}  ({info.get('bytes', 0):,} bytes)")
    print(f"  filas por tabla: {info.get('tables')}\n")

    antes = _radiografia(copia)

    # La app tiene que importarse DESPUÉS de fijar DATABASE_URL.
    os.environ["DATABASE_URL"] = f"sqlite:///{copia}"
    os.environ["APP_ENV"] = "dev"
    os.environ.setdefault("DATA_MODE", "mock")
    os.environ.setdefault("UPLOAD_DIR", os.path.join(tmp, "uploads"))
    from fastapi.testclient import TestClient

    from .main import app

    print("--- Primera pasada -------------------------------------------------")
    with TestClient(app):
        pass
    primera = _radiografia(copia)
    cambios = _diff(antes, primera)
    print("\n".join(cambios) if cambios else "  (sin cambios)")

    print("\n--- Segunda pasada sobre la MISMA copia (idempotencia) -------------")
    with TestClient(app):
        pass
    segunda = _radiografia(copia)
    repetidos = _diff(primera, segunda)
    print("\n".join(repetidos) if repetidos else "  (sin cambios)")

    fallos = []
    for tabla in ("users", "properties"):
        a = antes["tablas"].get(tabla, {}).get("filas")
        d = primera["tablas"].get(tabla, {}).get("filas")
        if a is not None and a != d:
            fallos.append(f"{tabla}: {a} -> {d} filas. Una migración no mueve filas de esta tabla.")
    if repetidos:
        fallos.append("la segunda pasada volvió a cambiar la base: no es idempotente.")

    print("\n" + "=" * 72)
    if fallos:
        for f in fallos:
            print(f"FALLO: {f}")
        print("=" * 72)
        return 1
    print("El ensayo pasa: la migración es idempotente y no mueve filas de")
    print("`users` ni de `properties`. La base original nunca se abrió para")
    print("escritura.")
    print("=" * 72)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    import sys

    if "--simular" not in sys.argv:
        print("Uso: python -m app.migrate --simular [ruta_a_la_base]")
        raise SystemExit(2)
    extra = [a for a in sys.argv[1:] if not a.startswith("-")]
    destino = extra[0] if extra else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "platform.db")
    raise SystemExit(_simular(destino))
