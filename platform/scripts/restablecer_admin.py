"""Vía de rescate del administrador (D-022).

El administrador **queda fuera** de la recuperación por correo, y es
deliberado: publicar un formulario que acepte su dirección reduciría toda la
cadena de URL oculta más segundo factor a «quien controle el buzón». Pero sin
una salida, la cuenta que lo ve todo se queda encerrada.

Esta es esa salida, y exige lo que un formulario no puede exigir: **estar
sentado delante de la máquina**.

Cubre las dos averías, que son distintas:

  - Se olvidó la contraseña      → `--contrasena`
  - Se perdió el teléfono (TOTP) → `--reiniciar-2fa`

Uso, desde `platform/`:

    python scripts/restablecer_admin.py --contrasena
    python scripts/restablecer_admin.py --reiniciar-2fa
    python scripts/restablecer_admin.py --contrasena --reiniciar-2fa --live

La contraseña se pide por teclado y no se muestra: así no queda en el
historial de la terminal ni en ninguna transcripción.

Por omisión trabaja sobre la base de simulación. Para tocar `platform.db`, que
tiene datos reales, hay que pasar `--live` y confirmar escribiendo el correo
completo: un error de tecleo no debe poder dejar sin acceso a una persona real.
"""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PLATFORM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ruta_base(live: bool) -> str:
    nombre = "platform.db" if live else "platform-mock.db"
    return os.path.join(PLATFORM_DIR, "data", nombre)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Rescata la cuenta de administrador desde la consola del servidor.")
    p.add_argument("--email", default=None,
                   help="Correo del administrador (por omisión, el único que haya)")
    p.add_argument("--contrasena", action="store_true", help="Poner una contraseña nueva")
    p.add_argument("--reiniciar-2fa", action="store_true",
                   help="Borrar el segundo factor para poder darlo de alta otra vez")
    p.add_argument("--live", action="store_true",
                   help="Usar platform.db (datos reales) en vez de la base de simulación")
    args = p.parse_args()

    if not args.contrasena and not args.reiniciar_2fa:
        print("Nada que hacer. Indica --contrasena, --reiniciar-2fa o las dos.")
        return 2

    ruta = _ruta_base(args.live)
    if not os.path.exists(ruta):
        print(f"ERROR: no existe {ruta}")
        return 1

    os.environ["DATABASE_URL"] = f"sqlite:///{ruta}"
    os.environ.setdefault("APP_ENV", "dev")
    os.environ["DATA_MODE"] = "live" if args.live else "mock"
    if args.live:
        # El candado legal protege el arranque de la aplicación, no esta
        # herramienta de rescate: aquí no se crean ni se leen datos de
        # inquilinos, solo se toca la credencial de un administrador.
        os.environ.setdefault("LEGAL_CLEARANCE_REF", "rescate-admin-consola")

    from app.auth import hash_password
    from app.db import SessionLocal
    from app.models import RoleEnum, User
    from app.security import MIN_PASSWORD_LEN, validar_fuerza_contrasena

    db = SessionLocal()
    try:
        q = db.query(User).filter(User.role == RoleEnum.admin)
        if args.email:
            q = q.filter(User.email == args.email.lower().strip())
        admins = q.all()
        if not admins:
            print("ERROR: no hay ninguna cuenta de administrador en esa base.")
            return 1
        if len(admins) > 1:
            print("Hay más de un administrador. Indica cuál con --email:")
            for a in admins:
                print(f"  - {a.email}")
            return 1
        admin = admins[0]

        print(f"\nBase:  {ruta}")
        print(f"Cuenta: {admin.email}")
        print(f"Acciones: {'contraseña ' if args.contrasena else ''}"
              f"{'segundo-factor' if args.reiniciar_2fa else ''}\n")

        if args.live:
            print("Esto toca DATOS REALES.")
            if input(f"Escribe «{admin.email}» para confirmar: ").strip() != admin.email:
                print("Cancelado.")
                return 1

        # Copia antes de escribir. Barata y salva de un error de tecleo.
        respaldo = f"{ruta}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(ruta, respaldo)
        print(f"Copia de seguridad: {respaldo}")

        if args.contrasena:
            nueva = getpass.getpass(f"Contraseña nueva (mínimo {MIN_PASSWORD_LEN}): ")
            problema = validar_fuerza_contrasena(nueva, getpass.getpass("Repítela: "))
            if problema:
                print(f"ERROR: {problema}")
                return 1
            admin.password_hash = hash_password(nueva)
            admin.password_changed_at = datetime.utcnow()
            admin.must_change_password = False
            admin.failed_login_count = 0
            admin.locked_until = None
            print("Contraseña cambiada, y el bloqueo por intentos fallidos levantado.")

        if args.reiniciar_2fa:
            admin.totp_secret = None
            admin.totp_enabled = False
            admin.totp_confirmed_at = None
            print("Segundo factor borrado: en el próximo acceso se vuelve a dar de alta.")

        db.commit()

        # Una credencial restablecida no puede seguir dando acceso donde ya
        # había sesión abierta: si se restablece porque se comprometió, dejar
        # sesiones vivas anula el propósito.
        from app.security import revoke_all_sessions
        try:
            cerradas = revoke_all_sessions(db, admin.id, "rescate_consola")
            print(f"Sesiones cerradas: {cerradas}")
        except Exception as exc:  # noqa: BLE001 — base antigua sin tabla sessions
            print(f"(no se pudieron cerrar sesiones: {exc})")

        print("\nListo. Entra por /login con la contraseña nueva.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
