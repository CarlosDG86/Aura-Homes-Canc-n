# Infraestructura — Reporte de estado

**Fecha:** 2026-09-08
**Periodo:** requisitos de infraestructura de la Fase 2.1
**Archivado en:** Aura/Reports/Infra/

---

## 1. Resumen

**Bloqueado en una cosa, y con un enlace roto en vivo.** La Fase 2.1 tiene **una sola
dependencia externa**: un buzón de correo de producción con SPF y DKIM. Sin él, el punto 3.2 del
CEO («olvidé mi contraseña») queda escrito e inservible. El plazo de aprovisionamiento no lo
controla Desarrollo, así que conviene abrirlo ya.

Además: el sitio público, que está arriba, enlaza a la plataforma de Fly, que está caída.

---

## 2. Estado actual

| Componente | Estado | Costo |
|---|---|---|
| Sitio público (Cloudflare Worker) | 🟢 Arriba — verificado HTTP 200 hoy | 0 USD |
| Plataforma (Fly) | 🔴 **No responde** — verificado HTTP 000 hoy | 0 USD |
| Respaldos automáticos | ⚫ Cancelados por el CEO | 0 USD |
| **Total** | | **0 USD** |

---

## 3. Bloqueadores

### 3.1 El sitio público enlaza a un host caído — EN VIVO

El menú «Ingresar» del sitio ofrece «Soy Propietario» y «Soy Inquilino», y ambos apuntan a
`https://aura-homes-plataforma.fly.dev`. Verificado hoy:

```
https://aura-homes-cancun.carlosdg0101.workers.dev/es/   HTTP 200   (el sitio está arriba)
https://aura-homes-plataforma.fly.dev/                   HTTP 000   (no responde)
https://example.com                                      HTTP 200   (había red)
```

Está en **22 páginas** de `dist/`. Cualquiera que pulse hoy recibe un error del navegador.
Fly se suspendió al acabar el periodo de prueba (decisión del CEO del 2026-08-12) y los enlaces
se quedaron.

Arreglarlo es un cambio en `data/site.json` y reconstruir. **Aviso: un `push` a `main`
republica el sitio público**, así que necesita aprobación explícita del CEO.

### 3.2 No hay correo de producción — bloquea el punto 3.2 (D-023)

Estado actual de `platform/.env`: `SMTP_HOST` y `SMTP_USER` tienen valor, **`SMTP_PASSWORD` está
vacío**. Con eso, el módulo de correo se queda en modo desarrollo y no envía nada.

Eso es también lo único que hoy contiene el defecto H-2 (ver el reporte de Legal): en cuanto se
llene esa contraseña, el modo simulación empezaría a enviar correos reales. **El arreglo de H-2
(etapa E10) tiene que ir antes o a la vez que la configuración del SMTP, nunca después.**

Para que la recuperación de contraseña funcione de verdad hace falta:

- Un buzón `no-responder@` en un dominio propio de Aura.
- Registros **SPF y DKIM** publicados en el DNS de ese dominio.
- Un proveedor: Google Workspace o Zoho son los dos candidatos de costo bajo.

Sin SPF y DKIM el correo cae en no deseados, el propietario cree que la plataforma está rota,
agota su límite de intentos y acaba llamando al CEO — que es exactamente el problema que la
función venía a resolver.

Esto se cruza con el dominio propio que Marketing lleva pidiendo desde el 2026-08-11:
`aurahomescancun.com` **sigue sin registrarse**, y el correo publicado en todas las páginas del
sitio (`hola@aurahomescancun.com`) no existe.

### 3.3 Almacenamiento sin dimensionar

El diseño de la Fase 2.1 añade documentos (facturas en PDF y XML), fotos del propietario al
cerrar tickets y paquetes de exportación. En el peor caso, un solo ticket puede ocupar ~145 MB
(5 fotos del inquilino + 10 del propietario + 5 documentos).

El disco de capa gratuita es de **1 GB compartido** con la base de datos, las fotos y los
paquetes. **No hay cuota por cuenta en ninguna etapa del diseño.** Hay que fijarla antes de E12.

### 3.4 Las pruebas no corren en el CI

Dos causas: el paso «Suite completa» se retiró del flujo de despliegue, y `test_migrate.py`
conserva rutas absolutas de Windows que no existen en el ejecutor de Linux.

---

## 4. Decisiones que esperan al CEO

**4.1 Enlaces rotos del sitio público.**
- A: Retirar el menú «Ingresar» hasta que la plataforma vuelva a estar en línea.
- B: Dejarlo como está.
- C: Apuntar a una página de mantenimiento.
- **Recomendación: A.** Es lo más honesto con quien visita el sitio y lo más barato de revertir.
  Requiere aprobación porque republica el sitio.

**4.2 (D-023) Buzón de correo de producción.**
- A: `no-responder@` en dominio propio de Aura, con Google Workspace o Zoho, y SPF/DKIM
  configurados por Infra.
- B: Reutilizar el buzón personal del CEO como remitente.
- C: No configurar SMTP y dejar la recuperación oculta.
- **Recomendación: A.** La B se descarta: un remitente personal en correo transaccional daña la
  reputación de envío y expone la dirección del CEO. Va ligada al registro del dominio, que sigue
  pendiente desde agosto.

**4.3 ¿Vuelve la plataforma a estar en línea, y dónde?**
- Fly ya no tiene capa gratuita para este caso. Antes de elegir sustituto conviene saber si el
  destino es una demostración a prospectos o un servicio con clientes reales — cambian los
  requisitos de disponibilidad y de respaldo.
- **Recomendación:** decidirlo después de E9, no antes: el trabajo local no lo necesita y hoy
  ningún dato real está en riesgo.

---

## 5. Próximos pasos

1. Decidir 4.1 — es lo único que un visitante ve roto hoy.
2. Abrir 4.2 con tiempo: es la ruta crítica del punto 3.2.
3. Fijar la cuota de almacenamiento por cuenta antes de construir E12.
4. Arreglar `test_migrate.py` y devolver el paso de pruebas al flujo automático.

---

## 6. Costo

| Concepto | Mensual |
|---|---|
| Hoy | 0 USD |
| Dominio propio (pendiente desde agosto) | ~1 USD (12–15 USD/año) |
| Buzón de correo con dominio propio | 0–6 USD |
| Hospedaje de la plataforma, si vuelve a estar en línea | por determinar |
