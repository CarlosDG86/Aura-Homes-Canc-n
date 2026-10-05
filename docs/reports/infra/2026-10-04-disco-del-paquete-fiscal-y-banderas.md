# Infraestructura — Reporte de estado

**Fecha:** 2026-10-04
**Periodo:** cierre de la Fase 2.1 — lo que hay que configurar antes de volver a encender nada
**Archivado en:** Aura/Reports/Infra/

---

## 1. Resumen

**En espera.** Nada cambió en producción: el sitio público sigue arriba en Cloudflare y la
plataforma sigue sin responder en Fly, suspendida por decisión del CEO. Los respaldos
automáticos siguen cancelados.

Lo que cambió es **lo que habrá que configurar el día que se vuelva a encender**: la Fase 2.1
añadió escritura en disco (fotos, comprobantes y ahora paquetes fiscales), nueve variables de
entorno nuevas y una tabla de banderas que conviene fijar antes y no después.

---

## 2. Lo nuevo que toca a Infraestructura

### 2.1 El disco dejó de ser irrelevante

Hasta la Fase 2 la aplicación solo escribía la base. Ahora escribe tres cosas:

| Qué | Dónde | Tope hoy |
|---|---|---|
| Fotos de tickets | `data/uploads` o `data/uploads-mock` | 8 MB por archivo, se recodifican |
| Comprobantes (PDF, XML, JPG, PNG) | el mismo árbol de subidas | 5 MB por archivo, 5 por ticket |
| **Paquetes fiscales (ZIP)** | `data/exports` o `data/exports-mock` | **200 MB por paquete** |

El volumen previsto es de **1 GB compartido** con la base y las fotos. Un paquete fiscal
**copia dentro** los comprobantes y, si se marca la casilla, las fotos; y el archivo se
conserva para poder volver a descargarlo.

**Consecuencia:** generar paquetes repetidamente llena el volumen. Hay tope por paquete, pero
**no hay purga de paquetes viejos**. Recomendación: antes de reactivar el hosting, definir una
retención (por ejemplo, conservar los dos últimos por año y cuenta) y vigilar el uso de disco.

Los directorios están **separados por modo**, igual que la base: los archivos de pruebas nunca
caen en la carpeta real, así que la purga de la época de pruebas es borrar una carpeta.

### 2.2 Variables de entorno nuevas

| Variable | Por omisión | Qué hace |
|---|---|---|
| `EXPORT_DIR` | `data/exports[-mock]` | Dónde se escriben los paquetes fiscales |
| `EXPORT_MAX_BYTES` | 200 MB | Tope de un paquete; si no cabe, se pide exportar por casa |
| `FISCAL_MODULE_ENABLED` | `true` | Apaga gastos, fiscal y exportación. Apagada devuelve 404 |
| `PROVIDERS_MODULE_ENABLED` | `true` | Apaga el directorio de proveedores |
| `TICKET_ATTACHMENTS_ENABLED` | `true` | Apaga fotos y comprobantes del propietario |
| `QUOTES_AGENT_ENABLED` | **`false`** | Cotización automática. Dejarla apagada |
| `PLAN_LIMITS_ENFORCED` | `true` | Apagarla deja de bloquear por límite de plan; **nunca** toca el aislamiento |
| `DOC_MAX_BYTES` / `MAX_DOCS_PER_TICKET` | 5 MB / 5 | Topes de comprobantes |
| `LEGAL_CLEARANCE_REF` | vacío | **Con `DATA_MODE=live` y sin esto, la aplicación no arranca** |

Todas se leen **en el servidor en cada petición relevante**, no solo al pintar el menú: ocultar
un botón no impide que alguien construya la petición a mano.

### 2.3 `PLAN_LIMITS_ENFORCED` es el interruptor de emergencia

Existe por una razón operativa concreta: si un fallo en la lógica de límites deja al CEO sin
poder dar de alta una casa un domingo, hace falta un interruptor documentado en vez de un
parche de madrugada —sobre todo con Fly suspendida, donde un redespliegue no es la vía rápida.
Solo afloja lo comercial, y cada alta que habría bloqueado queda en la bitácora.

---

## 3. El primer arranque contra la base real sigue siendo el momento delicado

Sin cambios respecto a septiembre, pero ahora con más carga: el primer arranque contra
`platform.db` descarga de golpe la deuda de esquema acumulada —8 tablas, unas 19 columnas y 20
índices, más las dos tablas nuevas de E14.

**Procedimiento obligatorio, en este orden:**

1. Instantánea del archivo de base.
2. `cd platform && python -m app.migrate --simular` (ensayo en seco; trabaja sobre una copia y
   no abre el original para escritura).
3. Confirmar que el ensayo dice que es idempotente y que no mueve filas de usuarios ni de
   propiedades.
4. Arrancar.

Ejecutado hoy: **pasa**, dos pasadas con diferencia vacía en la segunda, y el hash del archivo
original queda idéntico.

---

## 4. Bloqueadores

| Qué | Por qué | Qué lo desbloquea |
|---|---|---|
| Correo de la plataforma | Dominio sin registrar y sin buzón (D-023) | Registrar dominio y configurar SPF y DKIM |
| Enlaces «Ingresar» del sitio | Apuntan a un host que no responde, en 22 páginas | Decidir destino y aprobar el `push` que republica |
| Reactivar la plataforma | Suspendida por decisión del CEO | Decisión del CEO |
| Respaldos | Cancelados por decisión del CEO | Decisión del CEO; no se propone recuperarlos |

---

## 5. Decisiones esperando al CEO

- **Retención de paquetes fiscales.** Opción A: conservar todos (simple, llena el disco).
  Opción B: conservar los dos últimos por año y cuenta y borrar el resto (la fila queda como
  constancia aunque el archivo ya no esté; la pantalla lo muestra como «archivo retirado»).
  **Recomendación: B.**
- **Si se reactiva el hosting y cuándo**, porque fija el plazo del dominio y del buzón.

---

## 6. Próximos pasos

- Dejar escrito el procedimiento de arranque con instantánea en `DEPLOY.md` (hoy está en el
  documento de pendientes, no en el de despliegue).
- Añadir vigilancia de uso de disco antes de reactivar.
- Reponer el paso de suite completa en el flujo de despliegue.

---

## 7. Costo

Cero este periodo. Al reactivar: dominio, buzón y el volumen del hosting. Sin cifras todavía.
