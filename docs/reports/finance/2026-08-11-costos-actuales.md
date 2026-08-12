# Finanzas — Reporte de estado

**Fecha:** 2026-08-11
**Periodo:** Publicación de sitio y plataforma
**Archivado en:** Aura/Reports/Finance/

---

## 1. Resumen

**En marcha.** Dos aplicaciones publicadas en internet, con HTTPS y respaldos
automáticos, **por 0 USD al mes**. No hay ningún cargo recurrente activo ni
ningún método de pago comprometido.

---

## 2. Costo actual

| Concepto | Proveedor | Mensual |
|---|---|---|
| Sitio público | Cloudflare | 0 USD |
| Plataforma de gestión | Fly.io | 0 USD |
| Volumen de 1 GB (base y fotos) | Fly.io | 0 USD |
| Respaldos cifrados | GitHub Actions | 0 USD |
| Repositorio y automatizaciones | GitHub | 0 USD |
| **Total** | | **0 USD** |

Cómo se sostiene: la plataforma **se apaga sola cuando nadie la usa** y vuelve
a encenderse con la primera visita. Eso la mantiene dentro de la asignación
gratuita. El sitio público es estático — archivos servidos, sin servidor que
pagar.

---

## 3. En curso

Nada con impacto en costo.

---

## 4. Bloqueadores

Ninguno de índole financiera.

---

## 5. Decisiones que esperan al CEO

**5.1 Agente de inteligencia artificial para reportes de mantenimiento.**
Está construido y probado, hoy inactivo por falta de llave de API.

- Costo estimado: **~0.012 USD por reporte**, es decir **1–2 USD al mes** al
  volumen previsto.
- Sería **el primer cargo recurrente del proyecto**. Requiere aprobación
  explícita y un método de pago.
- Si no se aprueba: el inquilino llena un formulario manual. Funciona; solo es
  menos cómodo.
- **Recomendación:** posponerlo hasta que haya inquilinos reales usando la
  plataforma. Hoy pagaría por algo que nadie usa.

**5.2 Dominio propio.** Ver reporte de Marketing §5.2. Unos **12–15 USD al año**
(~1 USD al mes). Hoy el correo publicado en el sitio no existe, así que esto
tiene efecto comercial inmediato, no solo de imagen.

**5.3 Retención de respaldos.** Los respaldos se guardan 90 días, el máximo
gratuito. Conservar más tiempo exigiría almacenamiento de pago (unos pocos
dólares al año). **Recomendación:** 90 días es suficiente por ahora; revisarlo
cuando entren pagos reales (fase 2c).

---

## 6. Escenarios a futuro

Nada de esto está aprobado ni contratado; es para dimensionar.

| Si el proyecto crece hacia... | Costo aproximado |
|---|---|
| Dominio propio | ~1 USD/mes |
| Agente AI activo | 1–2 USD/mes |
| Base de datos gestionada (si SQLite se queda corta) | 5–25 USD/mes |
| Correo con dominio propio | 0–6 USD/mes |

El primer salto de costo real llegaría con la fase 2c (pagos), que exige
pasarela y probablemente contabilidad formal. No antes.

---

## 7. Próximos pasos

1. Decidir 5.2 — es el único con efecto comercial inmediato.
2. Mantener 5.1 en pausa hasta tener uso real.
3. Revisar este reporte cuando Legal firme y entren datos reales.
