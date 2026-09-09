# Fase 2.1 — Índice

**Fecha:** 2026-09-08 · **Estado:** diseño cerrado, construcción no iniciada

Este lote responde al feedback del CEO del 2026-09-07. Es el entregable de su punto 1:
*documentar el diseño antes de tocar código, para que los demás departamentos se pongan al día.*

**No hay código nuevo.** Nada de lo aquí descrito está construido.

---

## Por dónde empezar

| Si eres… | Lee |
|---|---|
| **El CEO** | [PLAN.md](PLAN.md), luego [DECISIONES_PENDIENTES.md](DECISIONES_PENDIENTES.md) |
| **Desarrollo** | [PLAN.md](PLAN.md) → [DB_SCHEMA.md](DB_SCHEMA.md) → el área que vayas a construir |
| **QA** | [`../reports/qa/2026-09-08-*`](../reports/qa/) y el plan de verificación por etapa |
| **Legal** | [`../reports/legal/2026-09-08-*`](../reports/legal/) — **corrige un punto del reporte de agosto** |
| **Infra** | [`../reports/infra/2026-09-08-*`](../reports/infra/) |
| **Finanzas** | [`../reports/finance/2026-09-08-*`](../reports/finance/) |
| **Diseño** | [`../reports/design/2026-09-08-*`](../reports/design/) |
| **Marketing** | [`../reports/marketing/2026-09-08-*`](../reports/marketing/) |

---

## Los documentos

| Documento | Qué contiene |
|---|---|
| [PLAN.md](PLAN.md) | Qué se pidió, dónde está diseñado, en qué orden se construye, qué lo bloquea |
| [DB_SCHEMA.md](DB_SCHEMA.md) | Esquema unificado, orden de migración, relleno de datos existentes. **Manda sobre los documentos de área** |
| [DECISIONES_PENDIENTES.md](DECISIONES_PENDIENTES.md) | D-017 a D-030, con opciones y recomendación |
| [HALLAZGOS_SEGURIDAD.md](HALLAZGOS_SEGURIDAD.md) | Dos defectos confirmados con prueba reproducible |
| [AREA_A_CUENTAS.md](AREA_A_CUENTAS.md) | Cuentas, planes, prueba gratuita, permisos por plan |
| [AREA_B_FISCAL.md](AREA_B_FISCAL.md) | Gastos, catálogo SAT/IRS, año fiscal, exportación para auditoría |
| [AREA_C_PROVEEDORES.md](AREA_C_PROVEEDORES.md) | Proveedores, archivos de ticket, cámara en móvil, cotizaciones |
| [AREA_D_PANEL.md](AREA_D_PANEL.md) | Panel del propietario, filtros, reportes |
| [AREA_E_ACCESO.md](AREA_E_ACCESO.md) | Ver contraseña, recuperación, cierre del agujero de la API |

El registro de decisiones vive ahora en git:
[`../decisions/DECISION_LOG.md`](../decisions/DECISION_LOG.md).

---

## Lo esencial en diez líneas

1. **Cuatro decisiones ya cerradas** (D-013 a D-016) fijan la cuenta como raíz de aislamiento,
   el español con cadenas extraídas, la vista de auditores como exportación, y los gastos bajo
   la puerta legal existente.
2. **Siete etapas, 28,5 días** de construcción: E8 a E14.
3. **E8 puede empezar hoy** y no depende de ninguna decisión. Es también la más urgente.
4. **Seis etapas están bloqueadas** por ocho decisiones del CEO.
5. **Tres defectos confirmados** con prueba reproducible; uno está en vivo en el sitio público.
6. La línea base de pruebas es **261 en verde**; el diseño añade 162 comprobaciones.
7. **Dos puntos del feedback quedan incompletos a propósito**: la automatización del 7.3 no
   tiene etapa, y el 7.4 se corta a media frase en el texto original — no se inventó el final.
8. Cuatro piezas transversales hay que **unificar antes** de escribir código, no durante.
9. `CLAUDE.md` **no se ha tocado**: describe un producto que ya no es el que se está
   construyendo, y su sección de producto requiere aprobación del CEO para cambiarse.
10. Los documentos están **redactados de datos personales**: los propietarios reales aparecen
    como «propietario #2» y «propietario #3», porque este lote se publica en Google Drive.
