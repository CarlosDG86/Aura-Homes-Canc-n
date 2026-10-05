# Desarrollo — Reporte de estado

**Fecha:** 2026-10-04
**Periodo:** cierre de la construcción de la Fase 2.1 (etapas E8 a E14)
**Archivado en:** Aura/Reports/Dev/

---

## 1. Resumen

**En marcha.** La Fase 2.1 está **construida completa** en la rama `work/feedback-usuarios`:
las siete etapas que respondían al feedback del CEO del 2026-09-07. Nada está publicado.

La suite de pruebas pasó de **261 comprobaciones** (línea base del 2026-09-08) a **722, en 17
suites, todas en verde**. El ensayo en seco de la migración contra la base real pasa, es
idempotente y deja el archivo original sin cambios.

Lo que queda abierto no es trabajo de Desarrollo: son decisiones del CEO y dos dependencias
externas (buzón de correo y firma de Legal).

---

## 2. Completado

| Etapa | Qué entrega |
|---|---|
| **E8** | Cierre del agujero de acceso por la API. Las tres rutas de `/api/auth/*` quedan retiradas; la sesión se resuelve en una sola función |
| **E9** | Cuentas como raíz de aislamiento (D-013), migración con relleno idempotente y matriz de planes |
| **E10** | Recuperación de contraseña, «ver contraseña», buzón de salida y cambio obligatorio de la clave temporal |
| **E11** | Panel del propietario: ocho indicadores, filtros por zona, recámaras, tamaño y ocupación, y descarga de la cartera |
| **E12** | Proveedores, comprobantes del ticket y cámara del teléfono |
| **E13** | Gastos desglosados, catálogo SAT/IRS, tipos de cambio y cierre de año fiscal |
| **E14** | Paquete fiscal para el contador, cotizaciones manuales y planes con efecto |

### 2.1 Lo que E14 añade, en concreto

- **Paquete fiscal (D-015).** Un ZIP por año, por casa o por cuenta: gastos, resumen por
  categoría con SAT e IRS lado a lado, reportes de mantenimiento, comprobantes originales,
  manifiesto, LEEME y los hashes de cada archivo. Se escribe a disco, nunca se arma en
  memoria, y tiene tope de tamaño configurable.
- **Pantalla intermedia obligatoria** antes de generar, con la casilla de fotos del interior
  **desmarcada**. Una petición que intente saltársela vuelve a la pantalla.
- **Cotizaciones manuales** en la ficha del ticket. Aprobar solo sella el estado y deja
  constancia: no avisa al proveedor ni cambia el ticket (D-017 pospuesta por el CEO).
- **Planes con efecto.** El límite de casas se aplica en las tres puertas de alta; la prueba
  vencida o la cuenta suspendida detienen las altas y **nada más**.

### 2.2 Dos correcciones de la prueba del CEO (2026-10-04)

- El icono de «ver contraseña» ya no reacciona al pasar el cursor.
- Un cambio de estado al estado que el ticket ya tiene avisa y no escribe nada. Antes se podía
  pulsar «Marcar en proceso» repetidamente y el historial acumulaba líneas idénticas.

---

## 3. En progreso

Nada. La construcción de la Fase 2.1 está terminada y commiteada. El siguiente trabajo depende
de decisiones ajenas a Desarrollo.

---

## 4. Bloqueadores

| Qué está bloqueado | Por qué | Qué lo desbloquea |
|---|---|---|
| Publicar cualquier cosa | Un `push` a `main` republica el sitio público | Aprobación explícita del CEO |
| Datos reales de inquilinos, proveedores y comprobantes | Puerta legal `DATA_MODE` (D-016) | Firma de Legal + confirmación del CEO |
| Enlaces «Ingresar» del sitio público (22 páginas) | Apuntan a Fly, que no responde | Decidir destino y aprobar el `push` |
| Ocupación real en el panel | 3 propiedades y **0 arrendamientos** cargados | Cargar los contratos (D-024, ya decidida) |
| Cierre del punto 7.4 | D-017 pospuesta | Que el CEO termine la frase «si el owner aprueba…» |

---

## 5. Decisiones esperando al CEO

- **D-017 — cómo termina el punto 7.4.** Hoy aprobar una cotización solo sella el estado.
  - Opción A: aprobar notifica al proveedor y agenda. Exige buzón de producción y define
    responsabilidad frente a un tercero.
  - Opción B: aprobar genera un gasto en borrador y nada más. Barato y reversible.
  - **Recomendación de Desarrollo: B**, y dejar la notificación para cuando exista el buzón.
- **Texto del descargo fiscal (D-027).** Está escrito y en pantalla, pendiente de revisión de
  abogado.
- **D-025 a D-030** siguen abiertas; ninguna frena la construcción.

---

## 6. Próximos pasos

- Cargar los contratos de arrendamiento en la base de pruebas para ver el panel con cifras
  reales de ocupación.
- Arreglar `test_migrate.py`, que conserva rutas absolutas de Windows y no imprime su línea de
  resultado, así que sus 7 comprobaciones no suman al total.
- Reponer el paso de suite completa en el flujo de despliegue.
- Decidir qué se hace con los enlaces «Ingresar» del sitio público.

---

## 7. Costo

Cero cargos nuevos. La plataforma sigue en local, sobre SQLite, sin servicios de pago. El
paquete fiscal consume disco en el volumen de la aplicación: ver el reporte de Infraestructura.
