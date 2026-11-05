"""Planes de suscripción y qué incluye cada uno (E9 · D-018, D-019).

**Esta plataforma no cobra.** Registra QUÉ plan tiene una cuenta; nunca cuánto
cuesta, ni cuándo vence una factura, ni si está pagada. El precio vive en el
sitio público y en el documento comercial (D-019). Cualquier importe aquí
sería el primer ladrillo de facturación, y la facturación cae bajo la puerta
legal de pagos, cerrada hoy por un 501 incondicional en `routers/payments.py`.

Reglas del CEO (D-018), en una sola tabla para que no vuelvan a divergir:

- Lo **manual** es gratis y está en todos los planes, incluido el de prueba:
  directorio de proveedores, captura de gastos y exportación fiscal. Retener
  los registros fiscales de un cliente tras un muro de pago es frágil — captura
  datos once meses y en marzo, con la auditoría encima, descubre que no puede
  sacar nada.
- Lo que se cobra es la **automatización**: agente de WhatsApp, cotización
  automática, paquete anual precalculado y gastos recurrentes.
- El sufijo **«+» significa siempre «agente»**. El nombre base significa
  escala.
- Superar el límite bloquea el alta de casas nuevas, jamás la lectura ni los
  tickets.

## Tramos vigentes — orden del CEO del 2026-10-14

| Plan | Casas |
|---|---|
| `trial` | 1, durante 90 días |
| `standard` | hasta 3 |
| `standard_plus` | de 4 a 7 |
| `enterprise` | de 8 a 20 |
| `enterprise_plus` | sin tope |

**Solo se guarda el techo de cada tramo.** El piso (que `standard_plus`
empiece en 4) es información comercial, no una regla que el servidor pueda
aplicar: bloquear a un cliente de `standard_plus` por tener *pocas* casas
sería negarle el alta por haber contratado de más.

Estos tramos **sustituyen** a los de septiembre (`standard` hasta 20,
`enterprise` sin tope). Son diez veces más estrechos, así que una cuenta que
hoy esté dentro de su plan puede quedar por encima del nuevo límite: eso **no
borra ni oculta nada**, solo impide crecer (ver `cuentas.estado_cuenta`).

## El agente de WhatsApp es exclusivo de los planes «+»

Decisión del CEO del 2026-10-29: el agente de IA sobre WhatsApp —responder,
precalificar y agendar visitas— es de los planes con «+». Los demás se quedan
con la automatización básica (mensajes automáticos de WhatsApp Business y la
página de citas de Google Calendar), que no pasa por la plataforma.

> ⚠️ **Tensión conocida, pendiente del CEO.** Hasta hoy `enterprise` heredaba
> el agente de `standard_plus` justamente para que un cliente de 20 casas no
> tuviera menos funciones que uno de 5. Aplicar la decisión del 29-oct al pie
> de la letra reintroduce esa asimetría, que es lo que el propio encargo a
> Finanzas pide revisar. Se aplica lo que está escrito y se deja la nota: si
> el CEO prefiere que `enterprise` conserve el agente, es **una celda de esta
> tabla**, sin migración ni cambios de esquema.
"""
from __future__ import annotations

#: Prueba gratuita por omisión (D-019). Sustituye a los 60 días de D-010.
TRIAL_DIAS_POR_OMISION = 90

#: Tope de seguridad para extender una prueba: un error de tecleo no debe
#: generar una prueba de veinte años.
TRIAL_DIAS_MAXIMO = 180

#: Cuántas casas admite el plan de prueba (punto 7.1: «just for one home»).
TRIAL_PROPIEDADES_MAX = 1

#: Derechos que una cuenta puede tener. Las claves se guardan en base y se
#: comparan por igualdad: **nunca se renombran**, solo se añaden.
AGENTE_MENSAJERIA = "agente_mensajeria"
COTIZACION_AUTOMATICA = "cotizacion_automatica"
FISCAL_AUTOMATIZADO = "fiscal_automatizado"
GASTOS_RECURRENTES = "gastos_recurrentes"

#: Derechos que tiene TODO el mundo, incluido el plan de prueba. Se listan
#: para que quede escrito, no para consultarlos con `tiene_derecho()`.
SIEMPRE_INCLUIDO = (
    "proveedores_crud",       # punto 5 del feedback
    "gastos_captura",         # punto 2.4
    "fiscal_export_manual",   # punto 2.3 y D-015
    "panel_y_filtros",        # puntos 2.1 y 2.2
    "acceso_y_recuperacion",  # punto 3: entrar nunca se cobra
)

PLAN_TRIAL = "trial"
PLAN_STANDARD = "standard"
PLAN_STANDARD_PLUS = "standard_plus"
PLAN_ENTERPRISE = "enterprise"
PLAN_ENTERPRISE_PLUS = "enterprise_plus"

#: `None` en `propiedades_max` = sin tope.
PLANES: dict[str, dict] = {
    PLAN_TRIAL: {
        "etiqueta": "Prueba (90 días)",
        "propiedades_max": TRIAL_PROPIEDADES_MAX,
        "derechos": frozenset(),
    },
    PLAN_STANDARD: {
        "etiqueta": "Standard",
        "propiedades_max": 3,
        "derechos": frozenset(),
    },
    PLAN_STANDARD_PLUS: {
        "etiqueta": "Standard +",
        "propiedades_max": 7,
        "derechos": frozenset({AGENTE_MENSAJERIA, FISCAL_AUTOMATIZADO, GASTOS_RECURRENTES}),
    },
    PLAN_ENTERPRISE: {
        "etiqueta": "Enterprise",
        "propiedades_max": 20,
        # Conserva la automatización fiscal —crecer no debe costar funciones—
        # pero NO el agente de WhatsApp, que el CEO reservó a los planes «+»
        # el 2026-10-29. Ver la advertencia del encabezado.
        "derechos": frozenset({FISCAL_AUTOMATIZADO, GASTOS_RECURRENTES}),
    },
    PLAN_ENTERPRISE_PLUS: {
        "etiqueta": "Enterprise +",
        "propiedades_max": None,
        "derechos": frozenset({AGENTE_MENSAJERIA, FISCAL_AUTOMATIZADO,
                               GASTOS_RECURRENTES, COTIZACION_AUTOMATICA}),
    },
}

#: Estados de cuenta. Igual que los planes: texto validado, no Enum().
ESTADO_ACTIVA = "activa"
ESTADO_SUSPENDIDA = "suspendida"
ESTADO_CERRADA = "cerrada"
ESTADOS = (ESTADO_ACTIVA, ESTADO_SUSPENDIDA, ESTADO_CERRADA)


def plan_valido(nombre: str) -> bool:
    return nombre in PLANES


def normalizar_plan(nombre) -> str:
    """Un plan desconocido leído de disco degrada a `trial`, no revienta.

    Degradar hacia el plan más restrictivo es la dirección segura: si la fila
    trae basura, la cuenta pierde funciones, nunca las gana.
    """
    return nombre if nombre in PLANES else PLAN_TRIAL


def normalizar_estado(estado) -> str:
    """Un estado desconocido degrada a `suspendida`, no a `activa`."""
    return estado if estado in ESTADOS else ESTADO_SUSPENDIDA


def etiqueta(plan: str) -> str:
    return PLANES[normalizar_plan(plan)]["etiqueta"]


def propiedades_max(cuenta) -> int | None:
    """Cuántas casas admite esta cuenta. `None` = sin tope.

    `properties_max_override` permite una excepción comercial puntual sin
    inventar un plan nuevo para un solo cliente.
    """
    if cuenta is None:
        return None
    override = getattr(cuenta, "properties_max_override", None)
    if override is not None:
        return override
    return PLANES[normalizar_plan(getattr(cuenta, "plan", None))]["propiedades_max"]


def tiene_derecho(cuenta, derecho: str) -> bool:
    """¿Puede esta cuenta usar esta función?

    Sin cuenta, no. Fallar cerrado es lo correcto aquí: mientras el relleno de
    `account_id` no haya terminado, un usuario sin cuenta no debe estrenar
    funciones de pago por accidente.
    """
    if cuenta is None:
        return False
    if normalizar_estado(getattr(cuenta, "status", None)) != ESTADO_ACTIVA:
        return False
    return derecho in PLANES[normalizar_plan(getattr(cuenta, "plan", None))]["derechos"]


def derechos_de(cuenta) -> dict:
    """Diccionario listo para inyectar en las plantillas.

    Devuelve **todas** las claves siempre, incluso sin cuenta. Jinja lanza
    `UndefinedError` al acceder a un atributo de una variable no inyectada, así
    que un `{% if feat.cotizacion_automatica %}` con la clave ausente rompería
    las 27 plantillas de golpe.
    """
    return {
        AGENTE_MENSAJERIA: tiene_derecho(cuenta, AGENTE_MENSAJERIA),
        COTIZACION_AUTOMATICA: tiene_derecho(cuenta, COTIZACION_AUTOMATICA),
        FISCAL_AUTOMATIZADO: tiene_derecho(cuenta, FISCAL_AUTOMATIZADO),
        GASTOS_RECURRENTES: tiene_derecho(cuenta, GASTOS_RECURRENTES),
    }
