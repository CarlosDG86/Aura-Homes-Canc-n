# Marketing — Reporte de estado

**Fecha:** 2026-08-11
**Periodo:** Publicación del sitio en internet
**Archivado en:** Aura/Reports/Marketing/

---

## 1. Resumen

**En riesgo.** El sitio ya es público y se ve bien, pero **de los siete
inmuebles publicados solo uno es inventario real**, y **el correo de contacto
que aparece en todas las páginas no existe**. Hoy el único canal que funciona
de verdad es WhatsApp.

| | Dirección |
|---|---|
| Sitio público | `https://aura-homes-cancun.carlosdg0101.workers.dev` |

---

## 2. Completado

- Sitio bilingüe (ES por defecto, EN) publicado con HTTPS y en el aire.
- Siete fichas con fotos, precios, características, requisitos y puntos de
  interés; cada una con su página propia en los dos idiomas.
- Botón de WhatsApp en todas las páginas, con mensaje previo cargado.
- Cabecera rediseñada: se redujo de 216 px a 60 px en móvil. La anterior se
  comía un tercio de la pantalla de un teléfono antes de que se viera una sola
  propiedad — y la mayoría de los interesados en renta llegan por celular.
- Logo optimizado: pasó de 1.5 MB a 39 KB, sin pérdida visible.

---

## 3. En curso

Nada en producción de contenido. El sitio está estable a la espera de decisiones
de este reporte.

---

## 4. Bloqueadores

### 4.1 El correo de contacto no existe — CRÍTICO

`hola@aurahomescancun.com` aparece en el pie de todas las páginas, en el
formulario y en el botón "Escríbenos por correo". **El dominio
`aurahomescancun.com` no está registrado** (no resuelve en DNS).

Consecuencia práctica: quien escriba a esa dirección recibe un rebote. El
formulario tampoco envía nada por su cuenta — abre el programa de correo del
visitante con ese destinatario —, así que **ninguna consulta por correo llega
hoy a nadie**.

Lo desbloquea: registrar el dominio, o cambiar el correo por uno que sí exista.

### 4.2 Seis de siete inmuebles no son inventario real

| Ficha | Qué es |
|---|---|
| Casa en La Rioja Residencial | **Real** — fotos y datos del inmueble del CEO |
| Casa en Residencial Cumbres | Demo con imágenes grises de relleno |
| Departamento SM 15 | Demo con imágenes grises de relleno |
| Lagos del Sol, Puerto Cancún, Cumbres, Arbolada | Cuatro fichas de prueba: fotos reales de casas, pero precios, zonas y descripciones **inventados** para probar el diseño |

Están publicadas y cualquiera puede verlas y preguntar por ellas. Es una
decisión de negocio, no técnica: quien escriba por la casa con alberca de
Puerto Cancún preguntará por algo que no está en renta.

### 4.3 Dirección provisional

`aura-homes-cancun.carlosdg0101.workers.dev` incluye el nombre de la cuenta
personal y no es una dirección que se pueda poner en un anuncio o una tarjeta.

---

## 5. Decisiones que esperan al CEO

**5.1 Qué hacer con las seis fichas que no son reales.**

- A: Retirarlas hasta tener inventario real. El sitio queda con una propiedad.
- B: Dejarlas y marcarlas visiblemente como muestra.
- C: Dejarlas como están.
- **Recomendación: A.** Un sitio con una propiedad real es honesto; uno con
  siete, de las que seis no existen, deja de serlo en cuanto alguien pregunta.
  Ya existe en el código un interruptor para ocultarlas sin borrarlas, así que
  volver atrás es inmediato.

**5.2 Dominio propio.**

- A: Registrar `aurahomescancun.com` (unos 12–15 USD al año) y apuntar ahí el
  sitio y el correo.
- B: Seguir con la dirección de `workers.dev` y cambiar el correo del sitio por
  uno que exista hoy (por ejemplo el Gmail del CEO).
- **Recomendación: A**, y B como parche inmediato mientras tanto — porque hoy
  el correo publicado simplemente no recibe nada.

**5.3 Número de WhatsApp.** El publicado es `+52 722 245 4472`, lada de Toluca.
Funciona igual, pero para un negocio de rentas en Cancún una lada 998 da más
confianza local. Decidir si se cambia o se deja.

---

## 6. Próximos pasos

1. Resolver 5.1 y 5.2 — son las dos que afectan a cualquiera que entre hoy.
2. Reunir fotos y textos del inventario real que se quiera publicar.
3. Medir el rendimiento en móvil (Lighthouse) — **todavía no se ha medido**;
   el objetivo de 90+ del plan sigue sin comprobarse.
4. Publicar aviso de privacidad y términos (ver reporte de Legal).

---

## 7. Costo

| Concepto | Mensual |
|---|---|
| Hospedaje del sitio | 0 USD |
| Dominio propio (si se aprueba 5.2 A) | ~1 USD (12–15 USD al año) |
