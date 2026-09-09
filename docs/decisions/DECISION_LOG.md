# Aura — Registro de decisiones

**Propósito:** fuente única de verdad de las decisiones del CEO. Los departamentos trabajan por
separado; este archivo es lo que evita que Desarrollo, Legal, Diseño, Finanzas y Marketing se
contradigan entre sí.

**Regla:** solo se añade. No se borran entradas; se marcan como sustituidas y se agrega la nueva.

**Copia canónica:** este archivo, en git. La copia de Google Drive
(`Aura/Decisions/DECISION_LOG.md`) es un espejo para lectura de los demás departamentos.

**Última actualización:** 2026-09-08

> **Nota de procedencia.** Hasta hoy este registro vivía **solo en Drive** y ningún documento
> del repositorio lo mencionaba. Eso permitió que `CLAUDE.md` siguiera describiendo el producto
> como una vitrina sin cuentas ni pagos mientras D-010 había cambiado el rumbo un mes antes.
> Las entradas D-000 a D-012 se traen aquí sin alterarlas.

---

## D-000 · Decisiones fundacionales (Charter)

| # | Decisión | Estado |
|---|---|---|
| 1 | Vitrina de propiedades del CEO — no marketplace | Vigente ⚠️ ver D-010 |
| 2 | Piloto en Cancún, Quintana Roo | Vigente |
| 3 | Arrendamiento a largo plazo | Vigente |
| 4 | Bilingüe ES/EN, español primario | Vigente (solo el sitio público — ver D-014) |
| 5 | Formulario de contacto + WhatsApp | Vigente |
| 6 | Stack estático de bajo costo | Vigente |

**Jurisdicción:** el brief original decía CDMX. **Correcto: Quintana Roo.** Afecta a los
documentos de renta (Código Civil de Q. Roo); privacidad y términos son de ley federal.

---

## D-010 · Pivote a SaaS multiempresa — DECISIÓN MAYOR

**Fecha:** 2026-08-11 · **Origen:** CEO · **Estado:** adoptada, con dependencias abiertas

El alcance cambia de *vitrina de las rentas del CEO* a **plataforma SaaS multiempresa vendida a
otras administradoras de propiedades**. Arquitectura multi-tenant desde el inicio.

Modelo de negocio registrado entonces: suscripción mensual, primeros clientes con **60 días
gratis** como *clientes fundadores*, precio inicial **$2,500 MXN/mes**.

> ⚠️ **En conflicto con el feedback del 2026-09-07**, que fija **90 días gratis para una sola
> casa**. Lo nuevo es posterior, pero el retiro formal de la regla de fundadores y el destino del
> precio están pendientes: ver **D-019**.

El showcase de La Rioja sigue vigente y convive con el SaaS como producto separado.

---

## D-011 · Nombre de la matriz — ABIERTA 🔴

`ORG_CHARTER.md` dice **Aura Enterprise Solutions**; la instrucción del pivote dice **Aura
Business Solutions**. Es el nombre que va en material de venta, contratos y facturación.
Sigue sin resolverse. `CLAUDE.md` usa hoy «Aura Enterprise Solutions».

---

## D-012 · Dónde vive el demo del SaaS — ABIERTA 🔴

Marketing recomendó la opción B (ruta o subdominio aparte, sin enlace en la navegación pública).
**Verificado en el código: hoy está implementada la opción A** — el enlace al demo está en la
navegación del sitio público desde el commit `32d22bc`. La decisión formal sigue abierta.

---

## D-013 · La cuenta es la raíz de aislamiento

**Fecha:** 2026-09-08 · **Estado:** cerrada

La unidad que se aísla y que porta el plan es la **cuenta/empresa**, no el usuario propietario.
Tabla `accounts` nueva; al migrar se genera una cuenta por cada propietario existente.

**Por qué:** hoy todo el aislamiento cuelga de `Property.owner_id`. Con clientes reales dentro,
rehacer esa frontera es mucho más caro y arriesgado que construirla ahora.

---

## D-014 · Español, con las cadenas extraídas

**Fecha:** 2026-09-08 · **Estado:** cerrada

Las pantallas nuevas se escriben en español, pero con los textos fuera de la plantilla, listos
para traducir. No se traduce nada todavía y no se construye i18n completo.

**Por qué:** la plataforma está hoy 100 % en español dentro de las plantillas. El feedback apunta
a auditorías del IRS y proveedores de EE. UU., así que el inglés llegará; extraer al escribir
cuesta poco y evita reescribir 27 plantillas después.

**Alcance:** aplica a la plataforma. La regla ES+EN de `CLAUDE.md` sigue vigente para el sitio
público.

---

## D-015 · «Auditors View» es una exportación, no un rol

**Fecha:** 2026-09-08 · **Estado:** cerrada

El propietario descarga un paquete por año fiscal y propiedad (datos, comprobantes e historial)
y se lo entrega a su contador. **No se crea rol de auditor** ni se abre acceso a terceros.

**Por qué:** un rol nuevo abre superficie de acceso a datos de inquilinos y obliga a rehacer las
27 comprobaciones de aislamiento. Un auditor del SAT o del IRS pide los datos, no una cuenta.

---

## D-016 · Gastos, comprobantes y proveedores bajo la puerta legal existente

**Fecha:** 2026-09-08 · **Estado:** cerrada

Se construyen ahora y se prueban en modo simulación; los datos reales entran cuando Legal firme,
igual que el resto de la plataforma. No se crea un criterio legal nuevo.

---

## D-018 · Matriz de planes: lo manual es gratis, lo automático se cobra

**Fecha:** 2026-09-08 · **Estado:** cerrada

- Directorio de proveedores, captura de gastos y exportación fiscal **manual**
  están en **todos** los planes, incluido el de prueba.
- Lo que se cobra es la **automatización**: agente de WhatsApp y correo,
  cotización automática, paquete anual precalculado y gastos recurrentes.
- El sufijo **«+» significa siempre «agente»**, y el nombre base significa
  escala: **Enterprise incluye todo lo de Standard+** más el volumen.
- **Límite: Standard hasta 20 propiedades; Enterprise a partir de 21.** Superar
  el límite bloquea el alta de casas nuevas, nunca la lectura ni los tickets.

**Por qué.** Resuelve dos contradicciones del feedback del 2026-09-07: el punto
5 daba los proveedores a todo propietario mientras el 7.2 los reservaba a
Enterprise+, y tal como estaba escrito un cliente de 25 casas tendría menos
funciones que uno de 5. Además, retener los registros fiscales de un cliente
tras un muro de pago es frágil: captura datos once meses y en marzo, con la
auditoría encima, descubre que no puede sacar nada.

---

## D-019 · La prueba de 90 días sustituye a los 60 días de D-010; el precio no entra en la plataforma

**Fecha:** 2026-09-08 · **Estado:** cerrada · **Sustituye a:** el modelo comercial de D-010

- **90 días de prueba para una sola casa**, para todos.
- La regla de **60 días para «clientes fundadores» queda retirada.** Un fundador
  pasa a ser una cuenta con la duración de prueba puesta a mano y una nota que
  explica por qué — no un segundo régimen con su propio camino de código.
- **El precio vive en el sitio público y en el documento comercial, nunca en la
  base de datos.** Cualquier importe dentro de la plataforma es el primer
  ladrillo de facturación, y la facturación cae bajo la puerta legal de pagos,
  hoy cerrada por un 501 incondicional.

---

## D-020 · Migración: una cuenta por propietario actual, sin límite y sin reloj

**Fecha:** 2026-09-08 · **Estado:** cerrada

Los dos propietarios de la base real reciben **una cuenta cada uno**, con plan
sin límite, sin prueba corriendo y marcadas «plan sin asignar» hasta que el CEO
decida. **Ambas se marcan como cuentas operadoras.**

**Por qué operadoras:** las tres propiedades reales llegaron por la
sincronización del sitio público. Si no se marcan así, la siguiente
sincronización deja de publicarlas el primer día.

**Por qué sin reloj de prueba:** el límite de una casa las pondría en falta
desde el primer momento, y el CEO viviría su propia plataforma como una avería.

---

## D-017 y D-021 a D-030 · Abiertas

Quedan **once** decisiones esperando al CEO, con opciones y recomendación en
[`docs/phase2.1/DECISIONES_PENDIENTES.md`](../phase2.1/DECISIONES_PENDIENTES.md).

**Cinco bloquean la construcción:**

| # | Qué falta | Bloquea |
|---|---|---|
| D-017 | Cómo termina el punto 7.4 («Si el owner aprueba…») | E14 |
| D-021 | Si «tickets» del punto 6.1 fue un lapsus por «fotos y comprobantes» | E12 |
| D-022 | Vía de emergencia del administrador, excluido de la recuperación por correo | E10 |
| D-023 | Buzón de correo de producción, SPF y DKIM — **dependencia externa** | E10 |
| D-024 | Cargar los contratos de arrendamiento y capturar fechas y renta | E11, E13 |

Cerradas el 2026-09-08: **D-018** (matriz de planes), **D-019** (prueba y precio) y
**D-020** (migración de los propietarios actuales). Con ellas, **E9 queda desbloqueada**.

---

## Requisitos derivados para otros departamentos

**Desarrollo**
- Arquitectura multi-tenant con aislamiento real entre cuentas (D-010, D-013).
- La galería del sitio público lee un arreglo ordenado desde la ficha de contenido, no del
  nombre de archivo.
- Sin datos estructurados de tipo `Product`/`Offer` en el showcase: no hay transacción.

**Legal**
- Encargado de datos de terceros bajo el modelo SaaS (D-010) — bloqueante antes del primer
  contrato con un cliente.
- Aviso de privacidad y términos del sitio público siguen sin texto mientras el formulario ya
  pide nombre, correo y teléfono.
- Retención de comprobantes fiscales y de fotos de tickets: pendiente (D-026).
- Todo documento legal es investigación o borrador, nunca asesoría; revisión de abogado mexicano
  titulado antes de publicar.

**Finanzas**
- El correo de producción (D-023) y el dominio propio son los dos primeros cargos recurrentes.
- El tope de gasto del agente de IA es hoy global; pasarlo a por cuenta es requisito antes del
  segundo cliente (D-028).

**Marketing**
- Dos audiencias opuestas: inquilinos (B2C) frente a administradoras (B2B).
- El precio no entra en la plataforma como importe hasta que se decida D-019.
