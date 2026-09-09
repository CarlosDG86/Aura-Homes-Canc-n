# Fase 2.1 — Plan de trabajo

**Fecha:** 2026-09-08 · **Estado:** diseño cerrado, construcción no iniciada
**Origen:** feedback del CEO del 2026-09-07
**Rama:** `work/feedback-usuarios` (local, nada publicado)

> **Nada de esto está construido todavía.** Este documento y los ocho que lo acompañan
> son el entregable del punto 1 del CEO: *"Create a solid design before proceeding with
> the dev changes, all needs to be updated and documented in git [and] Google drive for
> other departments to catch up."*

---

## 1. Qué pidió el CEO y dónde está diseñado

| Punto | Petición | Diseño | Etapa |
|---|---|---|---|
| 1 | Diseño sólido antes de codificar, documentado en git y Drive | **este lote de documentos** | entregado hoy |
| 2.1 | Panel: propiedades · inquilinos · tickets abiertos · ocupación % | [Área D](AREA_D_PANEL.md) | E11 |
| 2.2 | Filtros de casas por zona, tamaño y selección, para los reportes | [Área D](AREA_D_PANEL.md) | E11 |
| 2.3 | Módulo fiscal para auditorías del IRS (EE. UU.) y del SAT (México) | [Área B](AREA_B_FISCAL.md) | E13 |
| 2.4 | Gastos desglosados por propiedad y por ticket | [Área B](AREA_B_FISCAL.md) | E13 |
| 3.1 | Ver contraseña en el login | [Área E](AREA_E_ACCESO.md) | E10 |
| 3.2 | Olvidé mi contraseña para propietario e inquilino | [Área E](AREA_E_ACCESO.md) | E10 |
| 4 | Agente sobre angieslist.com | **fuera de alcance (Fase 3)** — verificado que no se coló | — |
| 5 | Proveedores: crear, modificar, eliminar | [Área C](AREA_C_PROVEEDORES.md) | E12 |
| 6.1 | Tras resolver, el propietario agrega documentos | [Área C](AREA_C_PROVEEDORES.md) | E12 |
| 6.2 | Fotos desde la cámara del teléfono; vista de auditores | [Área C](AREA_C_PROVEEDORES.md) · [Área B](AREA_B_FISCAL.md) | E12 · E14 |
| 7.1 | 90 días gratis para una sola casa | [Área A](AREA_A_CUENTAS.md) | E9 |
| 7.2 | Standard · Standard+ · Enterprise · Enterprise+ | [Área A](AREA_A_CUENTAS.md) | E9 · E14 |
| 7.3 | Automatizar y desglosar gastos por año y propiedad | [Área B](AREA_B_FISCAL.md) | E13 (desglose) · **sin etapa (automatización)** |
| 7.4 | email → ticket → cotización de proveedores → aprobación | [Área C](AREA_C_PROVEEDORES.md) | E14 (andamiaje) |

Dos casillas no están completas y conviene decirlo de frente:

- **7.3 «automatizar»** — el desglose manual está diseñado y tiene etapa; la automatización que
  distingue a los planes «+» (gasto en borrador al resolver un ticket, gastos recurrentes,
  comparativo entre años, aviso de comprobantes faltantes) **no tiene etapa asignada**. Es la
  mitad del punto que se cobra.
- **7.4** — su texto se corta en *"If owner approves"*. No se inventó el final: la máquina de
  estados queda abierta a propósito hasta que el CEO la cierre ([D-017](DECISIONES_PENDIENTES.md)).

---

## 2. Las cuatro decisiones que ya se tomaron

Se cerraron con el CEO el 2026-09-08 y son premisas, no opciones abiertas:

| # | Decisión | Consecuencia |
|---|---|---|
| D-013 | La raíz de aislamiento es la **cuenta/empresa**, no el usuario propietario | Tabla `accounts` nueva; una cuenta autogenerada por cada propietario actual |
| D-014 | **Español**, con las cadenas extraídas fuera de la plantilla | Sin traducir todavía; se evita reescribir 27 plantillas más adelante |
| D-015 | «Auditors View» = **exportación** por año fiscal y propiedad | Sin rol de auditor; no se toca el aislamiento para terceros |
| D-016 | Gastos, comprobantes y proveedores bajo la **puerta legal existente** | Se construyen ahora, se prueban en simulación, datos reales cuando Legal firme |

---

## 3. Secuencia de entrega

Siete etapas, continuando la numeración del repositorio (la última fue E7 y sigue sin hacerse).
**28,5 días de construcción** en total.

| Etapa | Qué entrega | Depende de | Esfuerzo |
|---|---|---|---|
| **E8** | Cierre del agujero de acceso por la API | nada | 0,5 día |
| **E9** | Cuentas, aislamiento por cuenta y migración completa | E8 | 5 días |
| **E10** | Recuperación de contraseña, ver contraseña, cambio forzado | E8 | 3 días |
| **E11** | Panel del propietario, filtros y reportes | E9 | 3 días |
| **E12** | Proveedores, archivos de ticket, cámara en móvil | E9 | 5 días |
| **E13** | Gastos desglosados y libro fiscal | E9 + E12 | 8 días |
| **E14** | Exportación para auditoría, cotizaciones y planes con efecto | E9 + E12 + E13 | 4 días |

**E8 no depende de ninguna decisión del CEO y puede empezar de inmediato.** Es también la de
mayor severidad: ver [HALLAZGOS_SEGURIDAD.md](HALLAZGOS_SEGURIDAD.md).

**E9 es la raíz.** Todo lo que el CEO pidió en los puntos 2, 5, 6 y 7 cuelga de que exista la
cuenta. No se puede adelantar E11, E12 ni E13 sin ella.

E10 comparte `auth.py` y `security.py` con E8: hacerlas en paralelo garantiza conflicto de fusión.

---

## 4. Qué bloquea la construcción hoy

Ocho decisiones del CEO ([D-017 a D-024](DECISIONES_PENDIENTES.md)) bloquean etapas concretas:

| Decisión | Bloquea |
|---|---|
| D-017 · cómo termina el punto 7.4 | E14 |
| D-018 · matriz de planes y límite de propiedades | E9, E14 |
| D-019 · 90 días frente a los 60 de D-010, y el precio | E9 |
| D-020 · a qué cuenta va cada propietario actual | E9 (**irreversible en la práctica**) |
| D-021 · si «tickets» del punto 6.1 fue un lapsus | E12 |
| D-022 · vía de emergencia del administrador | E10 |
| D-023 · buzón de correo de producción, SPF y DKIM | E10 (**dependencia externa, plazo fuera de Desarrollo**) |
| D-024 · cargar contratos de arrendamiento | E11, E13 |

D-024 es la de mayor efecto por unidad de esfuerzo: **hoy la base tiene 3 propiedades y
0 arrendamientos**, con una casa marcada como rentada en el sitio público. Sin contratos
cargados, el panel del punto 2.1 se entrega honesto y diciendo «Ocupación 0 %».

---

## 5. Lo que hay que unificar antes de escribir código

El crítico de completitud detectó cuatro cosas que los diseños de área resolvieron cada uno por
su cuenta y que chocarían al construir. **Se resuelven antes de E9, no durante:**

1. **Un solo módulo de cadenas.** El área C propone `app/strings/es.py` con una función `t()`;
   el área E propone `app/textos/acceso_es.py` como diccionario `T`. Gana `app/strings/es.py`.
2. **Un solo vocabulario de permisos por plan.** El área A usa `gastos_itemizados`,
   `proveedores_crud`…; el área C usa `providers.manage`, `tickets.attachments`… Hay que elegir
   uno: las claves se guardan en base y renombrarlas después es una migración.
3. **Los globales de Jinja.** Cuatro áreas añaden variables a `base.html`. Jinja 3.1 lanza
   `UndefinedError` al acceder a un atributo de una variable no inyectada, así que un
   `{% if feat.proveedores_crud %}` sin valor por defecto **rompe las 27 plantillas de golpe**.
4. **Seis banderas de módulo** que los diseños citan como marcha atrás y que no aparecen en
   ninguna etapa (`PLAN_LIMITS_ENFORCED`, `FISCAL_MODULE_ENABLED` y cuatro más).

---

## 6. Estado de las pruebas

Línea base medida el 2026-09-08 sobre la rama de trabajo:

```
TOTAL: 261 pasaron, 0 fallaron, en 10 suites
```

Se verificó además que ninguna suite toca `platform.db`: el hash del archivo es idéntico antes y
después de la ejecución completa.

El diseño añade **162 comprobaciones nuevas** repartidas por etapa. Tres cosas que QA debe saber:

- `tests/test_migrate.py` imprime sus 7 resultados pero **no la línea `RESULTADO:`**, así que
  hoy no suma al total y `run_all.py` lo da por bueno solo por su código de salida.
- Tres rutas absolutas de Windows sobreviven en `tests/test_migrate.py:3-4`; el trabajo en
  Linux del CI no puede ejecutar esa suite.
- La comprobación más importante de todo el lote es una **regresión**: que
  `POST /owner/tickets/{id}/actualizar` siga aceptando `application/x-www-form-urlencoded` y
  siga devolviendo 400 al resolver sin nota.

---

## 7. Documentos de este lote

| Documento | Qué contiene |
|---|---|
| [DB_SCHEMA.md](DB_SCHEMA.md) | Esquema unificado, orden de migración, relleno de datos. **Manda sobre los documentos de área.** |
| [HALLAZGOS_SEGURIDAD.md](HALLAZGOS_SEGURIDAD.md) | Dos defectos confirmados con prueba reproducible |
| [DECISIONES_PENDIENTES.md](DECISIONES_PENDIENTES.md) | D-017 a D-030, con opciones y recomendación |
| [AREA_A_CUENTAS.md](AREA_A_CUENTAS.md) | Cuentas, planes, prueba gratuita, permisos |
| [AREA_B_FISCAL.md](AREA_B_FISCAL.md) | Gastos, catálogo SAT/IRS, año fiscal, exportación |
| [AREA_C_PROVEEDORES.md](AREA_C_PROVEEDORES.md) | Proveedores, archivos de ticket, cámara, cotizaciones |
| [AREA_D_PANEL.md](AREA_D_PANEL.md) | Panel del propietario, filtros, reportes |
| [AREA_E_ACCESO.md](AREA_E_ACCESO.md) | Ver contraseña, recuperación, cierre del agujero |

Cómo se produjeron: 8 lectores mapearon el código existente contra el fuente; después, 3
arquitectos independientes diseñaron cada área desde ángulos distintos (mínimo viable, riesgo
primero, producto SaaS), un juez puntuó las tres y sintetizó la ganadora injertando lo mejor de
las perdedoras; por último, un integrador fundió las cinco áreas y un crítico buscó huecos y
afirmaciones sin verificar. Las citas a `archivo:línea` están comprobadas contra el código.
