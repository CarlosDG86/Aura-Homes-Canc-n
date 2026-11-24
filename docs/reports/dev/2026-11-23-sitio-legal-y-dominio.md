# Desarrollo — Reporte de estado

**Date:** 2026-11-23
**Reporting period:** a pedido del CEO
**Filed to:** Aura/Reports/Dev/2026-11-23.md

## 1. Status summary (3 lines max)
Overall: **At risk** — listo en la rama; publicar depende de una decisión del CEO sobre los textos legales.
El sitio queda sin ningún dato inventado, con correo propio, avisos legales preliminares, cookies con consentimiento y mejoras de accesibilidad.
El dominio `aurahomes.com.mx` no abría el sitio; el próximo despliegue lo conecta.

## 2. Completed since last report
Los 14 puntos del pedido, en `work/feedback-usuarios` (D-034):

| # | Pedido | Hecho |
|---|---|---|
| 1 | Política de cookies | Página bilingüe `politica-de-cookies` / `cookie-policy` |
| 2 | Integraciones con terceros | Página `servicios-de-terceros`: Cloudflare, Google, WhatsApp, OpenStreetMap, y lo que no se usa |
| 3 | Reseñas falsas | El sitio no tenía; lo falso eran las 7 fichas, ahora ocultas. `build.py` rechaza reseñas |
| 4 | Política de reembolsos | Página `pagos-y-reembolsos`: el sitio no cobra, aviso antifraude, depósito según contrato y ley local |
| 5 | Leyes locales | Cancún vigente; Dallas y Chicago preparados y marcados como «hoy no aplica» |
| 6 | Texto alternativo | Portada decorativa con `alt=""`, fotos numeradas, galería con `alt` dinámico |
| 7 | Consentimiento de cookies | Aviso con «Rechazar» y «Aceptar» del mismo peso; se reabre desde el pie |
| 8 | Copyright de imágenes | Leyenda en el pie, términos §5, y `photoRights` obligatorio para publicar una ficha |
| 9 | Accesibilidad | Salto al contenido, etiquetas ligadas, campos opcionales marcados, contraste AA, teclado en galería, movimiento reducido, declaración |
| 10 | Analítica | Cloudflare Web Analytics, sin cookies, solo con consentimiento y token |
| 11 | Etiquetas claras | «Términos y condiciones», «Por qué Aura» (antes «Zonas»), «Demo» con aviso de pestaña nueva, «(opcional)» |
| 12 | Términos Cancún / Dallas / Chicago | Términos §8 y §9 |
| 13 | Afirmaciones sin respaldo | Reescritas y bloqueadas en la compilación |
| 14 | No ser demandado | Todo lo anterior + paquete para abogado en `docs/legal/MARCO_LEGAL.md` |

Además: correo corregido a `@aurahomes.com.mx` (el anterior entregaba a un servidor ajeno) y dominio
del Worker en `wrangler.jsonc`. Suite de la plataforma: **831 de 831** comprobaciones en verde.

## 3. In progress
- Nada en curso.

## 4. Blockers
- Textos legales: la regla vigente pide revisión de abogado antes de publicar.
- Nombre legal y domicilio del responsable (aviso de privacidad).

## 5. Decisions awaiting the CEO
- **Publicar con textos legales preliminares o esperar al abogado.**
  - A: esperar revisión (cumple la regla; el sitio sigue sin aviso real mientras tanto).
  - B: publicar con la franja de «preliminar» (cubre el hueco hoy; no es asesoría).
  - Recomendación de Desarrollo: A si el abogado responde en días; B si tarda semanas.
- **Origen y licencia de `banner.jpg`.**

## 6. Next steps (before next report)
- Tras la aprobación: merge a `main` y push (pasos en `docs/DESPLIEGUE_DOMINIO.md`).
- Publicar la casa real del CEO cuando llegue la ficha de captura.

## 7. Budget/cost impact (if any)
- Ninguno. Cloudflare Web Analytics es gratuito.
