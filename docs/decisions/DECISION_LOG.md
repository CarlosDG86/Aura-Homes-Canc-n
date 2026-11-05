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

## D-021 · El punto 6.1 era «fotos y comprobantes», no tickets encadenados

**Fecha:** 2026-09-08 · **Estado:** cerrada

Tras resolver un ticket, el propietario adjunta **fotos del trabajo terminado y
comprobantes** (factura del proveedor). **No** se encadenan tickets derivados:
no se añade `parent_ticket_id` ni ruta para que el propietario cree tickets.
Encaja con el punto 6.2 («tomar fotos… al cerrarlos el owner»).

---

## D-022 · La vía de emergencia del administrador es un guión de consola

**Fecha:** 2026-09-08 · **Estado:** cerrada

El administrador **queda fuera** de la recuperación por correo, como pedía el
feedback («send a reset to owner and user role»). Su vía de rescate es
`platform/scripts/restablecer_admin.py`, con opción para reiniciar también el
segundo factor.

**Por qué.** Publicar un formulario que acepte el correo del administrador
reduciría toda la cadena de URL oculta más segundo factor a «quien controle el
buzón». Perder la contraseña y perder el teléfono son dos averías distintas y
el guión debe cubrir ambas.

---

## D-023 · Correo de producción: buzón propio con SPF y DKIM

**Fecha:** 2026-09-08 · **Estado:** cerrada, pendiente de ejecución por Infra

Buzón `no-responder@` en el dominio propio de Aura Homes (Google Workspace o
Zoho), con SPF y DKIM publicados. Entre 0 y 6 USD al mes.

Va ligado al registro de `aurahomescancun.com`, pendiente desde el 2026-08-11:
**el mismo registro arregla el correo roto del sitio público y habilita la
recuperación de contraseña.** Desarrollo prepara la configuración; el CEO crea
la cuenta y toca el DNS.

> ⚠️ **Orden obligatorio.** El arreglo del hallazgo H-2 (etapa E10) va **antes o
> a la vez** que la configuración del SMTP, nunca después: hoy lo único que
> impide que el modo simulación envíe correos reales con contraseñas en claro
> es que `SMTP_PASSWORD` está vacío.

---

## D-024 · Se cargan los contratos y se capturan fechas y renta

**Fecha:** 2026-09-08 · **Estado:** cerrada

Se añaden **fecha de inicio, fecha de fin y renta mensual** al formulario de
alta de inquilino que ya existe, y se cargan los 2-3 contratos reales.

**Por qué.** La base tiene 3 propiedades y 0 arrendamientos, con una casa
marcada como rentada en el sitio público: el panel diría «Ocupación 0 %» el
primer día. Los tres campos existen en `leases` desde hace meses y ninguna ruta
los escribe, así que «contratos por vencer», «renta contratada» y «antigüedad»
quedarían en «sin datos» para siempre, y el libro fiscal saldría sin ingresos.

---

## D-030a · La clave temporal obliga a cambiarla antes de usar la plataforma

**Fecha:** 2026-09-15 · **Estado:** cerrada · **Parte de:** D-030

Quien entra con una contraseña temporal no puede usar nada hasta poner una
propia. Afecta también a los inquilinos ya dados de alta.

**Por qué se preguntó:** `owner_portal.py` marca `must_change_password=True` en
cada inquilino que se crea, y hasta ahora ninguna ruta lo leía. Encenderlo
cambia el comportamiento de cuentas existentes.

**Por qué se pudo cerrar sin riesgo:** verificado antes de implementarlo —
`platform.db` no tiene siquiera la columna y no hay ningún inquilino real; los
dos que existen están en la base de pruebas. El CEO lo confirmó: son de prueba.

**Por qué importa:** mientras la persona conserve la clave que le dictó su
casero, quien se la dio puede entrar a su cuenta cuando quiera.

El resto de D-030 (los otros trece valores por defecto) sigue abierto.

---

## Órdenes del CEO del 2026-10-14 y 2026-10-29 (vía Google Drive)

Estas decisiones llegaron por Drive, no por el chat de Desarrollo, y durante tres
semanas el repositorio no las conoció. **Lo que diga Drive manda**; lo que sigue es
el espejo en git, con lo que cada una cambió del código ya construido.

Fuentes: «2026-10-14 — Orden del CEO: decisiones D-017 a D-024 y rediseño del panel
del propietario» y «2026-10-29 — Decisión del CEO: Agente de IA en WhatsApp solo en
el plan Plus», ambas en `Aura/` en Drive.

### D-017 · RESUELTA (2026-10-14) — aprobar una cotización sí tiene efectos

El propietario aprueba con un clic; esa acción **notifica al proveedor** y el ticket
pasa a «enviado a proveedor» / «en progreso».

**Sustituye a la entrada de más abajo**, donde el CEO había pedido posponerla. Lo
construido hoy solo sella el estado, así que esto es trabajo pendiente, y depende del
buzón de correo: sin dominio y sin Brevo no hay forma de avisar a nadie.

### D-018 · TRAMOS NUEVOS (2026-10-14) — diez veces más estrechos

| Plan | Casas |
|---|---|
| Standard | hasta 3 |
| Standard Plus | de 4 a 7 |
| Enterprise | de 8 a 20 |
| Enterprise Plus | sin tope |

Sustituye a «standard hasta 20, enterprise sin tope» de septiembre. **Aplicado en
`plans.py`.** Solo se guarda el techo de cada tramo: bloquear a un cliente por tener
*pocas* casas sería negarle el alta por haber contratado de más.

### D-019 · PRECIOS ORIENTATIVOS (2026-10-14)

Prueba de 90 días confirmada. Standard desde ~$2,000 MXN/mes y Enterprise ~$10,000
MXN/mes en Cancún, **sujetos a la cotización de mercado de Finanzas**; EE. UU. queda
pendiente, por estado. Los importes **siguen fuera de la plataforma**: viven en el
documento comercial.

### D-020 · LOS PROPIETARIOS ACTUALES SON FICTICIOS (2026-10-14)

El CEO declara que todos los propietarios del sistema son datos de prueba y que van a
la cuenta estándar.

> ⚠️ **Sin aplicar, a propósito.** La migración los dejó en `enterprise_plus` sin tope
> (ver la entrada D-020 de septiembre) y la regla de trabajo vigente dice que
> `platform.db` contiene propietarios reales del CEO. Además, la nota del 2026-10-14 a
> Marketing habla de **dos clientes pequeños reales**. Mover filas de cuenta y de plan
> sobre esa base sin resolver la contradicción es exactamente el tipo de cambio que no
> se deshace. **Pendiente de confirmación del CEO.**

### D-021 · CONFIRMADA Y AMPLIADA (2026-10-14)

Adjuntar documentos al ticket era intencional, y se añade un requisito: **un paquete
consolidado de tickets digitalizados** para el contador o una auditoría. El paquete
fiscal de E14 ya lo entrega (`tickets.csv` + `comprobantes/`). Falta lo que pide la
propia orden: **que Finanzas valide que esa documentación cumple requisitos fiscales**
antes de darlo por bueno.

### D-022 · CAMBIA DE FORMA (2026-10-14)

La vía de emergencia es un **reseteo forzado por el administrador verificado** que
genera credenciales nuevas —nunca un desbloqueo de la cuenta vieja—, con historial
auditado de quién, cuándo y a quién, y el **teléfono** como segundo dato para validar
identidad cuando se pierde el correo.

**Construido el 2026-11-04.** El administrador emite credenciales nuevas desde la ficha del
usuario: la clave la **genera el servidor** (antes la tecleaba el administrador, con un mínimo
de ocho caracteres cuando el de la plataforma son doce — la puerta de servicio era más débil
que la principal), hay que **confirmar los últimos cuatro dígitos del teléfono**, el motivo es
obligatorio, se cierran todas las sesiones y la persona debe cambiarla al entrar.

Si la ficha no tiene teléfono se puede seguir, pero marcándolo a mano, y el historial guarda
`identidad=sin_telefono`. Un intento con dígitos que no coinciden **no cambia nada y queda
registrado**: saber que alguien lo intentó es tan útil como saber que lo logró.

`/admin/reseteos` es la **primera pantalla que lee `audit_log`** — hasta hoy la bitácora existía
y nadie podía consultarla (D-029). Es de solo lectura y de tres acciones: volcarla entera sin
filtro no es una respuesta, es un vertido.

El guión de consola sigue siendo la salida cuando quien perdió el acceso es el propio
administrador: esta pantalla exige un administrador dentro.

### D-023 · RESUELTA (2026-10-14) — el correo es Brevo

Plan gratuito, 300 correos al día, SPF y DKIM con dominio propio, interfaz en español,
sin costo en esta fase. **Desbloquea la recuperación de contraseña**, que hoy no puede
salir de la plataforma. Depende de registrar el dominio.

### D-024 · RESUELTA (2026-10-14) — contratos ficticios por ahora

Se trabaja con datos de prueba; el CEO cargará los contratos reales cuando haya
propiedades reales arrendadas. **Deja de ser un pendiente del CEO**: el panel dirá
«Ocupación 0 %» hasta que existan contratos, y eso es correcto.

### D-031 · El agente de IA en WhatsApp es exclusivo de los planes «+» (2026-10-29)

Responder, precalificar y agendar visitas con IA es función de los planes con «+». Los
demás se quedan con la automatización básica: mensajes automáticos de WhatsApp Business
y la página de citas de Google Calendar, que no pasan por la plataforma. Motivo del CEO:
diferenciar el plan Plus como gancho comercial.

**Aplicado en `plans.py`**: `enterprise` pierde `agente_mensajeria` y conserva la
automatización fiscal. El asistente que redacta tickets —la única superficie de IA que
existe hoy— queda detrás del mismo derecho, y el formulario manual sigue en todos los
planes: reportar una avería no depende de lo que haya contratado el casero.

> ⚠️ **Tensión que el CEO debe cerrar.** `enterprise` tenía el agente justamente para que
> un cliente de 20 casas no tuviera menos funciones que uno de 5, y el encargo a Finanzas
> pide revisar esa asimetría. Se aplicó lo que está escrito. Revertirlo es una celda de la
> tabla de `plans.py`.

### D-032 · La agenda de visitas es la página de citas de Google Calendar (2026-10-29)

En lugar de Calendly. Afecta al sitio público y a la futura Fase B del agente, no a la
plataforma. El dominio entonces aprobado era `aurahomescancun.com` (~10 USD/año, Cloudflare
Registrar); **lo sustituyó D-033 el 2026-11-04**. **AUR-001 es ficticia: se elimina**; la primera propiedad real es la casa
del CEO.

---

### D-033 · El dominio oficial es aurahomes.com.mx (2026-11-04) — COMPRADO

**Sustituye a `aurahomescancun.com`**, que se había aprobado cinco días antes y nunca llegó
a registrarse. Motivo del CEO: `aurahomes.com` ya está tomado; un `.mx` da confianza local y
**no amarra la marca a Cancún**, de cara a otras ciudades.

El CEO confirma que **ya lo compró** (2026-11-04). Es el primer dominio que la empresa tiene
de verdad: hasta hoy el correo del pie de página rebotaba.

**Hecho en el repositorio:** el correo del sitio es `hola@aurahomes.com.mx`, las 24 páginas
están reconstruidas, los documentos de diseño apuntan a `app.aurahomes.com.mx` y `build.py`
**se niega a compilar** si el dominio viejo reaparece en `dist/`. QA pidió «verificar que no
quede ninguna referencia»; verificarlo a mano una vez no sirve, porque lo que falla es la vez
número doce.

Los reportes fechados **no se reescriben**: dicen lo que era cierto el día que se escribieron.

**Pendiente, y no es de Desarrollo:** apuntar los nameservers a Cloudflare, conectar Pages,
encender Email Routing hacia el Gmail del CEO y configurar «enviar como» con Brevo. Hasta que
eso exista, el correo del pie sigue sin recibir nada, solo que ahora el dominio sí es nuestro.

Dominio para EE. UU.: sin decidir.

---

## D-017 · Pospuesta — SUPERADA por la orden del 2026-10-14

**Fecha:** 2026-09-16 · **Estado:** histórica. El CEO cerró D-017 el 2026-10-14 (arriba);
esto describe por qué E14 se construyó sin ella y qué quedó preparado para cerrarla.

El texto del punto 7.4 se corta en *«If owner approves»*. En lugar de inventar el
final, E14 entrega las cotizaciones **manuales** y deja que aprobar o rechazar
**solo selle el estado** y escriba una línea en el historial del ticket.

Aprobar **no** avisa al proveedor, **no** agenda visita, **no** cambia el estado
del ticket, **no** asigna proveedor y **no** crea ningún pagadero. El diseño del
área C proponía asignar el proveedor si el ticket no tenía uno; **no se hizo**,
porque era justo la clase de efecto que D-017 tiene que decidir. `status` es texto
y no Enum: cerrar la frase mañana no exige tocar la base.

La cotización automática existe como ruta con cuatro cerrojos (plan Enterprise+,
`QUOTES_AGENT_ENABLED`, agente con llave y presupuesto, `DATA_MODE=live` con
autorización legal) y **en esta fase responde 501 aunque los cuatro estén
abiertos**: no hay nada construido detrás y no se hace ninguna llamada saliente.

---

## D-017 y D-025 a D-030 · Abiertas

Quedan **siete** decisiones esperando al CEO, con opciones y recomendación en
[`docs/phase2.1/DECISIONES_PENDIENTES.md`](../phase2.1/DECISIONES_PENDIENTES.md).

**Solo una bloquea la construcción:**

| # | Qué falta | Bloquea |
|---|---|---|
| D-017 | Cómo termina el punto 7.4 («Si el owner aprueba…») | Ya no bloquea: E14 se construyó sin ella por decisión del CEO |

Las otras seis (D-025 a D-030) no frenan la construcción: condicionan el paso a datos
reales de inquilinos y proveedores, o son valores por defecto ya fijados que solo
necesitan un visto bueno.

**Cerradas el 2026-09-08:** D-013 a D-016 (premisas de diseño), **D-018** (matriz de
planes), **D-019** (prueba y precio), **D-020** (migración), **D-021** (punto 6.1),
**D-022** (rescate del administrador), **D-023** (correo de producción) y **D-024**
(contratos de arrendamiento). Con ellas quedan desbloqueadas **E9 a E13**.

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
