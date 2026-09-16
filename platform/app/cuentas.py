"""Operaciones sobre cuentas. **El único sitio que escribe `account_id`.**

La columna `Property.account_id` es explícita y no derivada del dueño (ver
`models.Property`). Esa decisión solo vale algo si hay un único camino para
cambiarla: si cada ruta la escribiera por su cuenta, volveríamos a tener la
frontera entre clientes repartida por el código, que es exactamente lo que se
quería evitar.

Tres rutas mueven propiedades hoy, y ninguna sabía de cuentas:

- `POST /admin/users/{id}/properties` — reasignación manual del administrador.
- `POST /admin/sync-site-properties` — espejo del sitio público.
- `POST /api/admin/properties` — acepta `owner_id` en el cuerpo de la petición.

Todas pasan ahora por `transferir_propiedad()`, que mueve dueño y cuenta a la
vez y deja constancia. Cruzar la frontera de un cliente a otro deja de ser un
efecto colateral y pasa a ser una acción con nombre, registrada y bloqueable.

`PRAGMA foreign_keys` devuelve 0 en las dos bases, así que SQLite no impide
nada de esto: la integridad la sostienen el escritor único, el verificador del
arranque y una prueba con deriva inyectada a propósito.
"""
from __future__ import annotations

from typing import Optional

from .security import audit


class CruceDeCuentaBloqueado(Exception):
    """Se intentó mover una propiedad a otro cliente sin decirlo explícitamente."""


def cuenta_de(db, user) -> Optional[object]:
    """La cuenta de un usuario, o `None`."""
    from .models import Account

    if user is None or getattr(user, "account_id", None) is None:
        return None
    return db.get(Account, user.account_id)


def puede_publicar(cuenta) -> bool:
    """¿Puede esta cuenta escribir `site_ref`, es decir publicar en el sitio?

    Solo las cuentas operadoras de Aura. Sin cuenta, no: fallar cerrado evita
    que una cuenta a medio migrar estrene permisos por accidente.
    """
    return bool(cuenta is not None and getattr(cuenta, "is_operator", False))


def transferir_propiedad(db, request, prop, nuevo_owner, actor=None,
                         permitir_cruce_de_cuenta: bool = False,
                         motivo: str = "") -> bool:
    """Mueve una propiedad a otro dueño, arrastrando su cuenta. Devuelve si cambió.

    Si el dueño nuevo está en otra cuenta, esto es un **cruce de frontera entre
    clientes**: se lleva consigo los tickets de la casa, las fotos del interior
    de la vivienda y sus comprobantes fiscales. Por eso hay que pedirlo
    explícitamente con `permitir_cruce_de_cuenta=True`; en caso contrario
    levanta `CruceDeCuentaBloqueado` y no escribe nada.

    Queda siempre registrado en la bitácora, tanto el movimiento interno como
    el cruce, para que exista rastro aunque hoy ninguna pantalla lo lea.
    """
    if prop is None or nuevo_owner is None:
        return False

    cuenta_origen = prop.account_id
    cuenta_destino = getattr(nuevo_owner, "account_id", None)
    mismo_duenio = prop.owner_id == nuevo_owner.id
    misma_cuenta = cuenta_origen == cuenta_destino

    if mismo_duenio and misma_cuenta:
        return False

    if not misma_cuenta and not permitir_cruce_de_cuenta:
        audit(db, request, "cuenta.cruce_bloqueado", actor=actor,
              object_type="property", object_id=prop.id,
              meta=f"origen={cuenta_origen} destino={cuenta_destino}")
        raise CruceDeCuentaBloqueado(
            f"La propiedad #{prop.id} pertenece a la cuenta {cuenta_origen} y el "
            f"destinatario a la {cuenta_destino}. Mover datos entre clientes "
            f"exige confirmarlo explícitamente."
        )

    prop.owner_id = nuevo_owner.id
    prop.account_id = cuenta_destino

    audit(db, request,
          "cuenta.propiedad_cruzada" if not misma_cuenta else "cuenta.propiedad_reasignada",
          actor=actor, object_type="property", object_id=prop.id,
          meta=f"origen={cuenta_origen} destino={cuenta_destino} "
               f"duenio={nuevo_owner.id}{' motivo=' + motivo if motivo else ''}")
    return True


def asegurar_cuenta_de_usuario(db, usuario, creado_por=None) -> Optional[int]:
    """Da cuenta a un usuario recién creado. Devuelve el id de la cuenta.

    Existe porque el relleno de cuentas corre **una sola vez**, al arrancar, y
    marca la versión de esquema para no repetirse. Todo usuario creado después
    —un propietario dado de alta por el administrador, un inquilino dado de
    alta por su casero— nacía sin cuenta, y con `account_id` en NULL el
    aislamiento por cuenta responde 503 en vez de funcionar.

    Las dos reglas:

    - Un **propietario** estrena cuenta propia: es un cliente distinto.
    - Un **inquilino** entra en la cuenta de quien lo da de alta, que es la de
      la casa donde va a vivir. Nunca estrena una.
    """
    from .models import Account, RoleEnum

    if usuario is None or getattr(usuario, "account_id", None) is not None:
        return getattr(usuario, "account_id", None)

    rol = getattr(getattr(usuario, "role", None), "value", None)

    if rol == "owner":
        from . import plans

        cuenta = Account(
            name=usuario.name or f"Propietario #{usuario.id}",
            # Sin plan asignado y sin reloj de prueba corriendo: quién paga qué
            # lo decide una persona, no el alta (D-019, D-020).
            plan=plans.PLAN_TRIAL,
            status=plans.ESTADO_ACTIVA,
            plan_assigned_at=None,
            trial_started_at=None,
            primary_user_id=usuario.id,
            created_by_user_id=getattr(creado_por, "id", None),
        )
        db.add(cuenta)
        db.flush()
        usuario.account_id = cuenta.id
        return cuenta.id

    # Inquilino, o cualquier otro rol: hereda la cuenta de quien lo creó.
    heredada = getattr(creado_por, "account_id", None)
    if heredada is not None:
        usuario.account_id = heredada
    return heredada


def sincronizar_cuenta_con_duenio(db, prop) -> bool:
    """Pone la cuenta de la propiedad a la de su dueño. Devuelve si cambió.

    Para propiedades **recién creadas**, donde no hay frontera que cruzar
    porque todavía no pertenecen a nadie más.
    """
    from .models import User

    if prop is None:
        return False
    duenio = db.get(User, prop.owner_id)
    destino = getattr(duenio, "account_id", None) if duenio else None
    if destino is not None and prop.account_id != destino:
        prop.account_id = destino
        return True
    return False
