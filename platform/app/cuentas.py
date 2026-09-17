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


# --- Planes con efecto (E14 · D-018, AREA_A §4.6–4.8) ------------------------
#
# Regla en una línea: los límites se aplican al CREAR, nunca al LEER. Ninguna
# función de aquí oculta, archiva ni borra nada; lo peor que hacen es negarse
# a que la cartera crezca.


def limites_activos() -> bool:
    """`PLAN_LIMITS_ENFORCED`, encendida por omisión.

    Solo puede volver el sistema **más permisivo en lo comercial**. Nunca toca
    el aislamiento: apagarla no hace que nadie vea nada ajeno. Existe para que
    un fallo en esta lógica no deje al CEO sin poder dar de alta una casa.
    """
    import os

    return os.environ.get("PLAN_LIMITS_ENFORCED", "true").strip().lower() \
        not in {"0", "false", "no"}


def _ahora():
    from datetime import datetime, timezone

    # Ingenua en UTC: así vuelve SQLite y así se compara sin sorpresas.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ingenua(valor):
    return valor.replace(tzinfo=None) if valor is not None and valor.tzinfo else valor


def propiedades_usadas(db, cuenta_id) -> int:
    from .models import Property

    if cuenta_id is None:
        return 0
    return db.query(Property).filter(Property.account_id == cuenta_id).count()


def estado_cuenta(db, cuenta) -> dict:
    """Todo lo que la pantalla «Mi cuenta» y los bloqueos necesitan saber.

    Devuelve un diccionario plano, nunca el objeto del ORM, para que una
    plantilla no pueda tocar columnas que no debe.
    """
    from . import plans

    if cuenta is None:
        return {"tiene_cuenta": False, "plan": None, "etiqueta_plan": "Sin cuenta",
                "estado": None, "usadas": 0, "limite": None, "puede_crecer": True,
                "prueba_vencida": False, "dias_restantes": None,
                "puede_escribir": True, "motivo": "", "plan_sin_asignar": False}

    plan = plans.normalizar_plan(cuenta.plan)
    estado = plans.normalizar_estado(cuenta.status)
    usadas = propiedades_usadas(db, cuenta.id)
    limite = plans.propiedades_max(cuenta)

    fin = _ingenua(cuenta.trial_ends_at)
    vencida = plan == plans.PLAN_TRIAL and fin is not None and _ahora() >= fin
    dias = None
    if plan == plans.PLAN_TRIAL and fin is not None:
        dias = max(0, (fin - _ahora()).days)

    motivo = ""
    puede_escribir = True
    if estado != plans.ESTADO_ACTIVA:
        puede_escribir = False
        motivo = (f"La cuenta está {estado}. Puedes consultar todo y descargar tu "
                  f"exportación fiscal, pero no dar de alta nada nuevo.")
    elif vencida:
        puede_escribir = False
        motivo = ("Tu prueba de 90 días terminó. Todo sigue visible y descargable, "
                  "y tus inquilinos pueden seguir reportando averías; para dar de "
                  "alta algo nuevo hace falta elegir un plan.")

    puede_crecer = puede_escribir and (limite is None or usadas < limite)
    if puede_escribir and not puede_crecer:
        motivo = (f"Tienes {usadas} propiedad(es) y tu plan permite {limite}. "
                  f"No puedes añadir más; nada de lo que ya tienes se oculta.")

    return {"tiene_cuenta": True, "plan": plan, "etiqueta_plan": plans.etiqueta(plan),
            "estado": estado, "usadas": usadas, "limite": limite,
            "puede_crecer": puede_crecer, "prueba_vencida": vencida,
            "dias_restantes": dias, "puede_escribir": puede_escribir,
            "motivo": motivo, "plan_sin_asignar": cuenta.plan_assigned_at is None}


def _omitir_o_bloquear(db, request, actor, codigo: int, motivo: str,
                       accion: str, cuenta_id) -> None:
    from fastapi import HTTPException

    if not limites_activos():
        # La excepción no es invisible ni gratuita: queda una fila por cada
        # alta que se habría bloqueado.
        audit(db, request, "plan.limite_omitido", actor=actor,
              object_type="account", object_id=cuenta_id, meta=accion)
        return
    raise HTTPException(status_code=codigo, detail=motivo)


def exigir_cupo_de_propiedad(db, request, cuenta, actor=None) -> None:
    """409 si la cuenta no puede sumar una casa más.

    Se llama en las TRES puertas de alta. Un límite que cubre una sola puerta
    no es un límite. Va después de `OWNER_PROPERTY_MANAGE_ENABLED`: al revés,
    el mensaje no correspondería.
    """
    if cuenta is None:
        return
    est = estado_cuenta(db, cuenta)
    if est["puede_crecer"]:
        return
    _omitir_o_bloquear(db, request, actor, 409 if est["puede_escribir"] else 403,
                       est["motivo"], "alta_propiedad", cuenta.id)


def exigir_escritura(db, request, user) -> None:
    """403 si la cuenta está suspendida, cerrada o con la prueba vencida.

    Para las altas del día 91: inquilino, proveedor, gasto, cotización. **No**
    se llama al leer, al resolver un ticket, al descargar documentos ni al
    exportar, y jamás en la ruta con la que un inquilino reporta una avería:
    una fuga de agua no sabe nada de suscripciones.
    """
    cuenta = cuenta_de(db, user)
    if cuenta is None:
        return
    est = estado_cuenta(db, cuenta)
    if est["puede_escribir"]:
        return
    _omitir_o_bloquear(db, request, user, 403, est["motivo"], "escritura", cuenta.id)


def arrancar_prueba_si_toca(db, cuenta, prop) -> bool:
    """Arranca el reloj de 90 días al pasar de 0 a 1 propiedad. Devuelve si arrancó.

    El reloj está atado a la casa, no al alta de la cuenta: una cuenta vacía no
    tiene nada que caducar. Las tres columnas se escriben juntas y
    `trial_ends_at` se **materializa**, para que cambiar la constante mañana no
    mueva la fecha de nadie.
    """
    from datetime import timedelta

    from . import plans

    if cuenta is None or prop is None:
        return False
    if plans.normalizar_plan(cuenta.plan) != plans.PLAN_TRIAL:
        return False
    if cuenta.trial_started_at is not None:
        return False
    ahora = _ahora()
    dias = min(int(cuenta.trial_days or plans.TRIAL_DIAS_POR_OMISION),
               plans.TRIAL_DIAS_MAXIMO)
    cuenta.trial_started_at = ahora
    cuenta.trial_ends_at = ahora + timedelta(days=dias)
    cuenta.trial_property_id = prop.id
    return True
