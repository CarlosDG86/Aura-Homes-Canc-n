# Marco legal del sitio público — paquete para el abogado

**Fecha:** 2026-11-23 · **Preparado por:** Desarrollo · **Decisión:** D-034

> **Esto no es asesoría legal.** Es un inventario de lo que el sitio hace y de las normas que
> Desarrollo identificó, para que un abogado lo confirme o corrija. Ninguna cita de artículo
> aquí está verificada por un abogado.

## 1. Qué hace el sitio (hechos, no opiniones)

- Escaparate estático de casas en renta a largo plazo **propias del CEO**, en Cancún.
- **No cobra nada**, no tiene cuentas de usuario, no guarda datos: el formulario abre la app de
  correo del visitante con el mensaje armado.
- Contacto: correo (`info@` / `soporte@aurahomes.com.mx`, reenviado por Cloudflare a Gmail) y
  WhatsApp.
- Terceros que intervienen: Cloudflare (hospedaje, correo, analítica opcional sin cookies),
  Google (Gmail, Google Fonts), Meta (WhatsApp), OpenStreetMap (mapa en cada ficha).
- **Sin cookies propias.** Guarda en `localStorage` solo la respuesta al aviso de cookies.
- **Hoy no hay ninguna casa publicada** (las 7 eran ficticias; D-034).
- **No publica reseñas** y no puede compilar con un campo de reseñas.

## 2. Textos que hay que revisar

Están en `data/site.json` → `legalPages`, en español e inglés:
`privacy`, `terms`, `cookies`, `third`, `refunds`, `a11y`. Se ven compilados en
`dist/es/*.html` y `dist/en/*.html`. Mientras `brand.legalReviewed` sea `false`, cada uno lleva
una franja de «versión preliminar».

**Responsable:** persona física; nombre y domicilio en `brand.legalEntity` (2026-11-23). Falta el código postal.

## 3. México — Cancún, Quintana Roo (aplica hoy)

| Tema | Norma identificada | Dónde se refleja | Pregunta para el abogado |
|---|---|---|---|
| Datos personales | LFPDPPP vigente (nueva ley publicada en 2025) y su reglamento | Aviso de privacidad | ¿Basta aviso integral en el sitio? ¿Autoridad y plazos ARCO correctos tras la reforma? |
| Publicidad veraz | Ley Federal de Protección al Consumidor (información y publicidad veraz; comercio electrónico) | Reescritura de afirmaciones; términos §2 | ¿Las fichas requieren alguna leyenda adicional? ¿Aplica alguna NOM de prácticas comerciales en arrendamiento? |
| Arrendamiento | Código Civil para el Estado de Quintana Roo | Términos §8, reembolsos | Depósito: plazos y requisitos de devolución que conviene fijar en el contrato |
| No discriminación | Constitución art. 1; Ley Federal para Prevenir y Eliminar la Discriminación | Términos §3 | ¿Lista de motivos adecuada? |
| Jurisdicción | Tribunales de Cancún; Profeco | Términos §8 | ¿Cláusula válida frente a consumidores? |
| Propiedad intelectual | Ley Federal del Derecho de Autor | Pie de página, términos §5 | Origen y licencia de `banner.jpg` (ver §6) |

## 4. Estados Unidos — preparado, NO aplica todavía

El sitio dice expresamente que **hoy no ofrece casas en EE. UU.** Antes de publicar la primera:

**Dallas, Texas**
- Texas Property Code, cap. 92 (arrendamiento residencial): devolución del depósito y relación
  escrita de descuentos; divulgación de propietario/administrador.
- Texas Fair Housing Act y Fair Housing Act federal (incluida la publicidad: 42 U.S.C. §3604(c)).
- Texas Data Privacy and Security Act: confirmar si aplica a una empresa de este tamaño.

**Chicago, Illinois**
- Chicago Residential Landlord and Tenant Ordinance (RLTO, cap. 5-12): plazos de devolución del
  depósito, relación de daños con comprobantes, intereses sobre el depósito, resumen de la
  ordenanza anexo al contrato.
- Illinois Security Deposit Return Act.
- Illinois Human Rights Act y Chicago Human Rights Ordinance (incluye *fuente de ingresos*).
- Illinois BIPA: el sitio no recoge datos biométricos; confirmar que siga así.

**Ambos**
- Accesibilidad: ADA Title III; objetivo técnico WCAG 2.1 AA (declaración en `a11y`).
- FTC: regla de 2024 contra reseñas y testimonios falsos (16 CFR Part 465) — el sitio no publica
  reseñas.
- Pregunta abierta: ¿qué entidad y qué licencias (p. ej. licencia de bienes raíces de Texas o
  Illinois) se necesitan para anunciar casas ajenas en esos estados? Hoy solo serían casas propias.

## 5. Lo que Desarrollo dejó blindado en el código

`build.py` **no compila** si: aparece un correo `@aurahomes.com` (dominio ajeno); aparece una
afirmación sin respaldo («verificado», «sin stock», «garantizado», «menos de 24 horas», «el
mismo día», «el mejor»…); una ficha publicada no dice de quién son sus fotos (`photoRights`); una
ficha trae reseñas.

## 6. Riesgos abiertos

1. **`banner.jpg`** fue generada con IA (Google Gemini), según el CEO (2026-11-23). Lleva la
   leyenda «Imagen ilustrativa generada con IA» y lo dicen el pie y los términos §5. Pregunta:
   ¿basta con eso, y qué permiten los términos de uso de Gemini para uso comercial?
2. Responsable: Juan Carlos Davila Garcia, persona física, domicilio en Santiago Tianguistenco,
   Estado de México (falta el código postal). Pregunta: ¿conviene publicar un domicilio comercial
   en vez del particular?
3. `demo.html` (demostración de la plataforma) se publica en el sitio; no tiene datos de personas
   pero no se revisó con este criterio legal.
