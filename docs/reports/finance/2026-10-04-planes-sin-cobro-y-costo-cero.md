# Finanzas — Reporte de estado

**Fecha:** 2026-10-04
**Periodo:** cierre de la Fase 2.1 — qué registra la plataforma sobre planes y qué no
**Archivado en:** Aura/Reports/Finance/

---

## 1. Resumen

**En marcha, sin cargos nuevos.** La Fase 2.1 se construyó entera en local: SQLite, sin
servicios de pago, sin hosting activo. Los respaldos automáticos siguen cancelados y la
plataforma de Fly sigue suspendida, las dos por decisión del CEO.

La novedad para Finanzas es que **los planes ya tienen efecto en el producto**: la plataforma
registra qué plan tiene cada cuenta y lo hace cumplir. **Sigue sin cobrar nada y sin saber
ningún precio.**

---

## 2. Lo que la plataforma registra de un plan, y lo que no

**Sí registra:** qué plan tiene cada cuenta, su estado (activa, suspendida, cerrada), cuántos
días de prueba le quedan, cuántas casas usa frente a su límite, quién le asignó el plan, cuándo
y con qué nota de respaldo.

**No registra, por diseño:** importes, moneda de cobro, ciclo de facturación, si una factura
está pagada, CLABE, IBAN, tarjeta, RFC ni domicilio fiscal.

Cualquier importe ahí sería el primer ladrillo de facturación, y la facturación cae bajo la
puerta legal de pagos, hoy cerrada. El precio vive en el documento comercial (D-019), fuera de
la base de datos.

---

## 3. La matriz vigente (D-018), tal como está construida

| Plan | Casas | Lo manual | Agente WhatsApp/correo | Gastos automáticos | Cotización automática |
|---|---|---|---|---|---|
| Prueba (90 días) | 1 | ✅ | — | — | — |
| Standard | hasta 20 | ✅ | — | — | — |
| Standard + | hasta 20 | ✅ | ✅ | ✅ | — |
| Enterprise | sin tope | ✅ | ✅ | ✅ | — |
| Enterprise + | sin tope | ✅ | ✅ | ✅ | ✅ |

«Lo manual» incluye el panel y los filtros, el directorio de proveedores, la captura de gastos,
el registro de cotizaciones y **el paquete fiscal para el contador**. Está en todos los planes,
incluida la prueba.

### 3.1 Dónde está el argumento comercial

**El paquete de marzo es la demostración que convierte.** Un propietario que capturó sus gastos
durante la prueba y en marzo descarga un ZIP que su contador acepta, tiene una razón concreta
para pagar. Si en cambio descubre que no puede sacar nada, la prueba se convierte en un
agravio. Por eso lo manual no se cobra y la exportación sigue disponible incluso con la cuenta
suspendida.

**Lo que se cobra es la automatización:** que la máquina hable con el proveedor, genere el gasto
y pida la cotización. Eso tiene costo marginal real —llamadas a un modelo de pago y correo
saliente— y por eso se puede defender un precio.

### 3.2 Excepciones sin inventar planes

Hay dos palancas para un caso comercial puntual, las dos con nota obligatoria y registro:
un **tope de casas propio** para esa cuenta, y **extender la prueba** hacia adelante, con techo
de 180 días. Es el mecanismo para «clientes fundadores» de D-010: no se construye un segundo
régimen.

---

## 4. Costos previsibles cuando esto arranque

| Partida | Estado | Nota |
|---|---|---|
| Dominio propio | **Sin registrar** | Bloquea el correo del sitio y la recuperación de contraseña |
| Buzón de correo de producción (D-023) | **Sin contratar** | Primera dependencia externa; su plazo no lo controla Desarrollo |
| Hosting de la plataforma | Suspendido | Volumen de 1 GB cuando se reactive |
| Llave del agente de IA | Sin contratar | El tope de gasto es **global**, no por cuenta |
| Respaldos | Cancelados | Decisión del CEO; no se propone recuperarlos |
| Revisión de abogado | Sin cotizar | Bloquea el paso a datos reales |

### 4.1 Un riesgo de costo que conviene anotar

El paquete fiscal ocupa disco: los comprobantes y las fotos se copian dentro del ZIP y el
archivo se conserva para poder volver a descargarlo. Con el volumen de 1 GB compartido con la
base y las fotos, generar paquetes repetidamente lo llena. Hay un tope por paquete (200 MB) y
está anotado en el reporte de Infraestructura; lo que **no** hay todavía es una política de
purga de paquetes viejos.

### 4.2 El tope del agente de IA sigue siendo global

Sin cambios desde septiembre (D-028). Un cliente con muchas averías consumiría el presupuesto
de todos. Hay que pasarlo a por cuenta **antes del segundo cliente**, no después.

---

## 5. Decisiones esperando al CEO

- **Precio de cada plan** (D-019). Sin él no hay página de precios ni documento comercial.
- **Si el directorio de proveedores debe cobrarse.** Hoy es gratis en todos los planes.
  Cambiarlo es **una celda de una tabla**: ni esquema, ni migración, ni rutas.
- **Fecha objetivo** para el primer cliente externo, que es lo que fija la urgencia del dominio,
  el buzón y la revisión legal.

---

## 6. Próximos pasos

- Cotizar dominio y buzón de producción para tener una cifra real que presentar.
- Definir purga de paquetes fiscales antes de reactivar el hosting.

---

## 7. Costo del periodo

**Cero.** Ningún cargo nuevo desde el 2026-09-08.
