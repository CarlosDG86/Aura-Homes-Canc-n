# Marketing — Reporte de estado

**Fecha:** 2026-10-04
**Periodo:** cierre de la Fase 2.1 — qué se puede prometer y qué todavía no
**Archivado en:** Aura/Reports/Marketing/

---

## 1. Resumen

**En espera.** El sitio público no cambió y sigue arriba. Lo que cambió es el producto que hay
detrás: la plataforma de administración está construida completa, en local y sin publicar.

Para Marketing eso significa que **ya existe una lista cerrada de funciones que se pueden
prometer sin mentir**, y una lista igual de clara de las que no. Y sigue existiendo un problema
visible al público que no se ha arreglado: el menú «Ingresar» lleva a un error.

---

## 2. Lo que ya se puede prometer

| Función | Nota para el mensaje |
|---|---|
| Panel con propiedades, inquilinos, tickets abiertos y % de ocupación | Cada indicador lleva impresa su definición debajo |
| Filtros por zona, recámaras, tamaño y ocupación | Y descarga de la cartera en CSV |
| Reportes de mantenimiento con fotos desde el teléfono | La cámara se abre desde el navegador, sin instalar nada |
| Directorio de proveedores | Alta, edición, archivado y borrado |
| Gastos desglosados por casa y por reporte | Con comprobante en PDF, XML, JPG o PNG |
| **Organización fiscal para SAT e IRS** | 15 categorías con doble mapeo |
| **Paquete para el contador** | Un archivo por año que el propietario descarga y entrega |
| Registro de cotizaciones para comparar precios | Manual, en todos los planes |
| Recuperación de contraseña y «ver contraseña» | |

### 2.1 La frase que mejor vende, y es verdad

**«En marzo, descargas un archivo y se lo das a tu contador.»** El paquete lleva los gastos del
año, el resumen por categoría con los conceptos del SAT y del IRS lado a lado, los reportes de
mantenimiento y los comprobantes originales.

Dos matices que **conviene decir en el material**, porque sostienen credibilidad:

- **No calcula impuestos y no decide qué es deducible.** Organiza y entrega. Eso lo dice la
  propia pantalla, y es lo que un contador quiere oír.
- **Los datos de los inquilinos no salen.** En el paquete aparecen como «Inquilino #contrato».
  Para una administradora que maneja casas de terceros, eso es un argumento, no una limitación.

---

## 3. Lo que NO se puede prometer todavía

| No prometer | Por qué |
|---|---|
| Agente de WhatsApp o correo | Construido y probado, **desconectado**, sin llave de API |
| Cotización automática a proveedores | Es un esqueleto con cuatro cerrojos; responde «todavía no disponible» |
| Correo desde `hola@aurahomescancun.com` | El dominio **no está registrado** |
| Cualquier cosa con datos reales de inquilinos | Detrás de la puerta legal hasta que Legal firme |
| Búsqueda en Angie's List (punto 4 del feedback) | Fase 3, fuera de alcance |
| Precios | No están decididos (D-019) |

---

## 4. Los planes, para la página de precios

| Plan | Casas | Lo que lo distingue |
|---|---|---|
| Prueba | 1 casa, 90 días | Todo lo manual, incluido el paquete fiscal |
| Standard | hasta 20 | Multi-propiedad |
| Standard + | hasta 20 | **El «+» significa agente**: WhatsApp/correo y gastos automáticos |
| Enterprise | sin tope | Escala |
| Enterprise + | sin tope | Agente, gastos automáticos y cotización automática |

**El «+» siempre significa «agente».** El nombre base significa escala. Conviene que el material
lo diga así, en esas palabras, porque es la confusión más probable del cliente.

**Lo manual nunca se cobra** —panel, filtros, proveedores, gastos y el paquete fiscal están en
todos los planes, incluida la prueba— y **la exportación sigue funcionando incluso si la cuenta
se suspende**. Es una promesa que se puede poner por escrito: *tus datos fiscales no quedan
secuestrados por una suscripción*.

---

## 5. El problema visible que sigue abierto

El menú «Ingresar» ofrece «Soy Propietario» y «Soy Inquilino» en **22 páginas** y las dos llevan
a un host que no responde: quien pulse recibe un error del navegador. Es lo primero que vería
un cliente curioso que llegue del material de marketing.

Arreglarlo es cambiar un archivo de configuración y reconstruir, pero **republica el sitio** y
necesita aprobación del CEO. Opciones: quitar el menú hasta que la plataforma vuelva, o
apuntarlo a una página que explique que el acceso es por invitación.

---

## 6. Decisiones esperando al CEO

- **Qué se hace con «Ingresar».** Recomendación de Marketing: apuntarlo a una página propia de
  «acceso por invitación» con el formulario de contacto, que convierte un error en un contacto.
- **Precios y nombres finales de los planes** (D-019).
- **Si el material se dirige a propietarios individuales o a administradoras**, que son dos
  audiencias opuestas. Sin esto, la página de precios no se puede escribir.

---

## 7. Costo

Cero. El dominio sigue sin registrar y es la primera partida en cuanto haya fecha.
