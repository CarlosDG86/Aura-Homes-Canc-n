"""Restablece la contraseña de una cuenta en la base LOCAL.

Existe porque las contraseñas se guardan con bcrypt, que es de una sola vía:
si se olvida una, no hay forma de recuperarla — solo de poner otra. Eso es
deseable (nadie con acceso al archivo puede leerlas), pero deja al CEO fuera de
su propia instalación local si no la recuerda.

La contraseña se pide por teclado y no se muestra: así no queda en el historial
de la terminal ni en ninguna transcripción.

Uso, desde `platform/`:

    python scripts/reset_local_password.py admin@aura-homes-cancun.local

Por seguridad solo funciona contra la base de simulación. Para tocar
`platform.db`, que contiene datos reales, hay que pasar --live de forma
explícita y confirmar: un error de tecleo no debe poder cambiar la contraseña
de una persona real.
"""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MIN_LEN = 8


def main() -> int:
    p = argparse.ArgumentParser(description="Restablece una contraseña en la base local.")
    p.add_argument("email", help="Correo de la cuenta")
    p.add_argument("--live", action="store_true",
                   help="Usar platform.db (datos reales) en vez de la base de simulación")
    args = p.parse_args()

    db_name = "platform.db" if args.live else "platform-mock.db"
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(here, "data", db_name)

    if not os.path.exists(db_path):
        print(f"No existe {db_path}", file=sys.stderr)
        return 1

    if args.live:
        print(f"ATENCIÓN: vas a modificar {db_name}, que contiene datos reales.")
        if input("Escribe 'si' para continuar: ").strip().lower() != "si":
            print("Cancelado.")
            return 1

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.setdefault("APP_ENV", "dev")

    from app.auth import hash_password          # noqa: E402
    from app.db import SessionLocal             # noqa: E402
    from app.models import User                 # noqa: E402

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email.lower().strip()).first()
        if not user:
            print(f"No hay ninguna cuenta con el correo {args.email}", file=sys.stderr)
            print("Cuentas disponibles:", file=sys.stderr)
            for u in db.query(User).order_by(User.id):
                print(f"   {u.email}  ({u.role.value})", file=sys.stderr)
            return 1

        nueva = getpass.getpass("Nueva contraseña (no se muestra): ")
        if len(nueva) < MIN_LEN:
            print(f"Debe tener al menos {MIN_LEN} caracteres.", file=sys.stderr)
            return 1
        if nueva != getpass.getpass("Repítela: "):
            print("No coinciden.", file=sys.stderr)
            return 1

        # Copia antes de escribir: si algo sale mal, la base anterior sigue ahí.
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        respaldo = f"{db_path}.bak-{marca}"
        shutil.copy2(db_path, respaldo)

        user.password_hash = hash_password(nueva)

        # Si la cuenta estaba bloqueada por intentos fallidos, se desbloquea:
        # de poco sirve restablecer la contraseña si el bloqueo sigue activo.
        for campo, valor in (("failed_login_count", 0), ("locked_until", None),
                             ("must_change_password", False), ("is_active", True)):
            if hasattr(user, campo):
                setattr(user, campo, valor)

        db.commit()
        print(f"\nListo. Contraseña de {user.email} ({user.role.value}) actualizada en {db_name}.")
        print(f"Copia previa: {os.path.basename(respaldo)}")

        # Las sesiones abiertas con la contraseña anterior no deben seguir vivas.
        try:
            from app.security import revoke_all_sessions
            n = revoke_all_sessions(db, user.id, "password_reset")
            db.commit()
            if n:
                print(f"Se cerraron {n} sesión(es) abiertas.")
        except Exception:
            pass

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
