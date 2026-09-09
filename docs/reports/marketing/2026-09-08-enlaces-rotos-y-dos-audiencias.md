# Marketing — Reporte de estado

**Fecha:** 2026-09-08
**Periodo:** revisión del sitio público frente a la Fase 2.1
**Archivado en:** Aura/Reports/Marketing/

---

## 1. Resumen

**En riesgo.** Dos cosas que un visitante encuentra hoy y que no funcionan: el menú «Ingresar»
lleva a un servidor caído, y el correo de contacto que aparece en todas las páginas sigue sin
existir. Ninguna es nueva; la primera se detectó hoy, la segunda lleva abierta desde el
2026-08-11.

---

## 2. Lo que un visitante encuentra hoy

Verificado sobre el sitio en vivo:

| Elemento | Estado |
|---|---|
| Sitio público | 🟢 Responde |
| Menú «Ingresar» → Soy Propietario / Soy Inquilino | 🔴 **Error de navegador**, en 22 páginas |
| `hola@aurahomescancun.com` | 🔴 El dominio no está registrado; los correos rebotan |
| Botón de WhatsApp | 🟢 Funciona |
| Enlace DEMO en la navegación | 🟢 Funciona |
| 6 de 7 fichas de propiedad | 🟡 No son inventario real |

Las mediciones:

```
https://aura-homes-cancun.carlosdg0101.workers.dev/es/   HTTP 200
https://aura-homes-plataforma.fly.dev/                   HTTP 000   ← el destino de «Ingresar»
```

El servidor de la plataforma se suspendió el 2026-08-12 al acabar el periodo de prueba de Fly.
Los enlaces del sitio se quedaron apuntando ahí.

**Consecuencia comercial:** el sitio ofrece a propietarios e inquilinos un acceso que no existe.
Para un prospecto B2B —una administradora evaluando el producto— es peor que no tener el enlace.

---

## 3. Sobre el enlace DEMO (D-012)

Marketing recomendó en agosto la opción B: ruta o subdominio aparte, sin enlace en la navegación
pública. **Verificado: hoy está implementada la opción A** — «DEMO» aparece en la navegación
principal del sitio, junto a Propiedades, Cómo funciona y Contacto.

La observación de entonces sigue en pie: `aurahomescancun.com` es la vitrina para **inquilinos**,
y poner ahí la entrada al producto SaaS (a) confunde a quien buscaba casa y (b) enseña el
producto a la competencia junto al inventario propio. La decisión formal sigue abierta.

---

## 4. Bloqueadores

### 4.1 El correo publicado no existe — ABIERTO desde el 2026-08-11

Sin cambios. `hola@aurahomescancun.com` aparece en el pie de todas las páginas, en el formulario
y en el botón «Escríbenos por correo». El dominio no está registrado. **Toda consulta que no
llegue por WhatsApp se pierde sin dejar rastro.**

Esto se cruza ahora con la Fase 2.1: el punto 3.2 del CEO («olvidé mi contraseña») necesita un
buzón de producción, y ese buzón necesita el mismo dominio. **Las dos cosas se resuelven con el
mismo registro.**

### 4.2 Seis de siete fichas no son inventario real

Sin cambios desde agosto. Ya existe en el código un interruptor para ocultarlas sin borrarlas.

---

## 5. Decisiones que esperan al CEO

**5.1 Menú «Ingresar» roto.**
- A: Retirarlo hasta que la plataforma vuelva a estar en línea.
- B: Dejarlo.
- C: Apuntar a una página que explique que el acceso está en mantenimiento.
- **Recomendación: A.** Un enlace ausente no cuesta nada; uno roto sí. **Aviso: republica el
  sitio público**, así que necesita aprobación explícita.

**5.2 Dominio propio.** Sigue pendiente desde agosto, y ahora bloquea también una función de la
plataforma.
- **Recomendación:** registrarlo (12–15 USD al año). Resuelve el correo del sitio y habilita el
  buzón que necesita la recuperación de contraseña.

**5.3 (D-012) Dónde vive el demo.** Confirmar la opción A que ya está implementada, o pasar a la
B recomendada por Marketing.

---

## 6. Próximos pasos

1. Resolver 5.1 — es lo único que un visitante ve roto hoy.
2. Registrar el dominio: desbloquea dos cosas a la vez.
3. Cerrar D-012 antes de que existan prospectos B2B mirando.

---

## 7. Costo

| Concepto | Mensual |
|---|---|
| Retirar los enlaces rotos | 0 USD |
| Dominio propio | ~1 USD (12–15 USD/año) |
