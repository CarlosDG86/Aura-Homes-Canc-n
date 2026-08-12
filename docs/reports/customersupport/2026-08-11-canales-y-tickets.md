# Atención a Clientes — Reporte de estado

**Fecha:** 2026-08-11
**Periodo:** Publicación de sitio y plataforma
**Archivado en:** Aura/Reports/CustomerSupport/

---

## 1. Resumen

**En riesgo.** El sistema de reportes de mantenimiento está completo y probado,
pero aún sin inquilinos reales. Del lado del sitio público, **de los tres
canales de contacto anunciados solo funciona uno**: WhatsApp.

---

## 2. Estado de los canales

### 2.1 Sitio público — para interesados en rentar

| Canal | Estado |
|---|---|
| **WhatsApp** | ✅ Funciona. Botón en todas las páginas, con mensaje precargado |
| Formulario de contacto | ❌ Abre el correo del visitante hacia una dirección que no existe |
| "Escríbenos por correo" | ❌ Misma dirección inexistente |

`hola@aurahomescancun.com` aparece en todo el sitio, pero el dominio
`aurahomescancun.com` no está registrado. Quien escriba recibe un rebote, y
nadie se entera de que hubo una consulta. Detalle en el reporte de Marketing §4.1.

**Consecuencia operativa:** hoy, toda consulta que no llegue por WhatsApp se
pierde en silencio.

### 2.2 Plataforma — para inquilinos ya instalados

Construido, probado y funcionando en modo simulación:

- **Reportes de mantenimiento con fotos.** El inquilino describe el problema y
  adjunta hasta cinco imágenes.
- **Detección de urgencias del lado del servidor.** Un reporte que mencione gas,
  fuego o inundación se eleva a emergencia **aunque el inquilino haya marcado
  prioridad baja**. Se decidió así porque quien vive el problema no siempre
  sabe cuán grave es.
- **Historial y comentarios** en cada reporte, visibles para ambas partes.
- **Resolver exige explicar qué se hizo.** No se puede cerrar un reporte en
  blanco.
- **Reporte por unidad** con descarga en CSV, para ver qué vivienda concentra
  incidencias.
- **Bandejas en ambos sentidos** entre propietario e inquilino, con contador de
  mensajes sin leer, más comunicados a todos o por propiedad.
- **Contacto directo al propietario** por correo o WhatsApp desde el panel del
  inquilino.

Se probó con dos propietarios y dos inquilinos: ninguno ve nada del otro.

---

## 3. En curso

Nada en construcción.

---

## 4. Bloqueadores

| Bloqueador | Qué impide |
|---|---|
| Correo inexistente | Recibir consultas que no lleguen por WhatsApp |
| Sin firma de Legal | Dar de alta inquilinos reales |
| Sin llave de API | El asistente que arma el reporte conversando |

El asistente de inteligencia artificial está construido y probado. Sin llave,
el inquilino llena un formulario manual: funciona igual, solo es menos cómodo.
Ver reporte de Finanzas §5.1.

---

## 5. Decisiones que esperan al CEO

**5.1 Arreglar el correo.** Ver Marketing §5.2. Desde atención a clientes es lo
más urgente de todo el proyecto: es el único punto donde **se está perdiendo
contacto con clientes potenciales hoy mismo**, sin que quede rastro.

**5.2 Tiempos de respuesta comprometidos.** El sitio promete responder pronto,
pero no hay un compromiso definido ni quién lo cumple. Conviene fijarlo antes de
tener volumen — sobre todo para las emergencias, donde el sistema ya distingue
la urgencia pero no hay nadie asignado a atenderla.

---

## 6. Próximos pasos

1. Arreglar el correo (5.1).
2. Recorrido completo con datos ficticios: levantar un reporte, resolverlo,
   revisar el reporte por unidad.
3. Definir tiempos de respuesta (5.2).
4. Cuando Legal firme: dar de alta al primer inquilino real y acompañarlo en su
   primer reporte.

---

## 7. Costo

Sin impacto, salvo el agente AI si se aprueba (1–2 USD/mes).
