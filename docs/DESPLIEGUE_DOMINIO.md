# Publicar el sitio en aurahomes.com.mx — pasos para el CEO

**Fecha:** 2026-11-23 · **Rama:** `work/feedback-usuarios` · **Decisión:** D-034

Solo el **sitio público**. La plataforma no se publica: Fly está suspendida por decisión tuya.

## Cómo está hoy (comprobado el 2026-11-23)

| | Estado |
|---|---|
| Zona `aurahomes.com.mx` en Cloudflare | ✅ nameservers `cullen` / `alexandra.ns.cloudflare.com` |
| Correo `@aurahomes.com.mx` (Email Routing) | ✅ registros MX de Cloudflare activos |
| `aurahomes.com.mx` abre el sitio | ❌ **no resuelve**: ningún registro apunta al Worker |
| Sitio en la URL `workers.dev` | ✅ responde 200, con la versión de `main` |
| `aurahomes.com` | ⚠️ **no es tuyo en Cloudflare**: su correo va a `gridhost.com` |

## Antes de publicar: una decisión tuya — ✅ decidida el 2026-11-23: camino B

Las seis páginas legales son **borradores** escritos por Desarrollo, con una franja que lo dice.
La regla del registro de decisiones es que un texto legal no se publica sin revisión de abogado.
Dos caminos:

- **A (recomendado):** el abogado revisa `docs/legal/MARCO_LEGAL.md` y las páginas; cuando firme,
  se pone `"legalReviewed": true` en `data/site.json` y la franja se cambia sola por la fecha.
- **B:** publicas ya con la franja de «versión preliminar». Hoy esas páginas dicen «se publicará
  muy pronto» mientras el formulario pide datos; un borrador honesto es menos riesgo que nada,
  pero sigue sin ser asesoría.

## Pasos (en este orden)

1. **Revisa en tu máquina** lo que se va a publicar:
   ```
   python build.py --serve
   ```
2. **Publica** (republica el sitio; solo con tu aprobación):
   ```
   git checkout main
   git merge work/feedback-usuarios
   git push
   ```
   Cloudflare compila y despliega. Con `routes` en `wrangler.jsonc`, ese despliegue **crea solo**
   el registro DNS y el certificado de `aurahomes.com.mx` y `www.aurahomes.com.mx`.
3. **Si el despliegue falla por permisos del dominio** (el token de compilación no puede tocar la
   zona), hazlo a mano, un minuto: Cloudflare → *Workers & Pages* → `aura-homes-cancun` →
   *Settings* → *Domains & Routes* → *Add* → *Custom domain* → `aurahomes.com.mx`; repite con
   `www.aurahomes.com.mx`.
4. **Comprueba**: abre `https://aurahomes.com.mx/es/` en el teléfono. Debe salir el aviso de
   cookies y «Estamos preparando nuestras primeras propiedades».
5. **Analítica (opcional):** Cloudflare → *Analytics & Logs* → *Web Analytics* → *Add a site* →
   `aurahomes.com.mx` → elige **instalación manual (JS snippet)**, **no** la automática (la
   automática inyecta el script sin pedir consentimiento). Copia el `token` del fragmento a
   `data/site.json` → `analytics.cloudflareBeaconToken`, recompila y publica igual que en el paso 2.
6. **Correo:** manda un correo de prueba a `info@` y `soporte@aurahomes.com.mx` y confirma que
   llega a tu Gmail.

## Para publicar tu casa real después

En `data/properties.json`, la ficha nueva necesita: quitar `placeholder`, llenar `photoRights`
(por ejemplo «Fotos tomadas por el propietario en noviembre de 2026»), y en `dist/.assetsignore`
añadir `!assets/img/<id>/`. Sin `photoRights` el sitio **no compila**, a propósito.
