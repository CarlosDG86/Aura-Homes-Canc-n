# Legal — Reporte de estado

**Fecha:** 2026-09-08
**Periodo:** revisión de la Fase 2.1 y corrección del reporte del 2026-08-11
**Archivado en:** Aura/Reports/Legal/

---

## 1. Resumen

**En riesgo.** Este reporte corrige una afirmación del anterior: **una de las barreras técnicas
que se dieron por implementadas no lo está**. El modo simulación no impide enviar correo real en
todas las rutas, y el defecto se activa justo al construir lo que el CEO pidió el 2026-09-07.

Los bloqueadores del reporte anterior siguen abiertos: el sitio público continúa pidiendo datos
personales con un aviso de privacidad que dice que se publicará «muy pronto».

---

## 2. Corrección al reporte del 2026-08-11

El reporte anterior listó, entre las barreras ya puestas: **«No envía correos reales.»**

Verificado hoy contra el código: **para el restablecimiento de contraseña del administrador, eso
no es cierto.** La función que envía el correo
(`platform/app/email_utils.py:63`) nunca consulta el modo simulación; solo comprueba si el SMTP
está configurado. La guarda `emails_are_sent()` existe únicamente en dos llamadas de
`owner_portal.py`.

Reproducido interceptando el envío, sin conectar con ningún servidor:

```
DATA_MODE=mock?     True
emails_are_sent()?  False   ← la plataforma afirma que no envía
Resultado: sent=True configured=True
>>> SE INTENTÓ ENVIAR a persona.real@gmail.com, con la contraseña EN CLARO
```

**Riesgo hoy:** contenido. Lo único que lo detiene es que `SMTP_PASSWORD` está vacío en la
configuración local. `SMTP_HOST` y `SMTP_USER` sí tienen valor.

**Riesgo mañana:** el punto 3.2 del feedback («olvidé mi contraseña») **exige** configurar ese
SMTP. El día que se llene ese campo, el modo simulación empezaría a enviar correos reales con
contraseñas en claro. El diseño de la Fase 2.1 lo corrige moviendo la guarda dentro del módulo
de correo, que es donde debió estar: así no puede olvidarse en la siguiente ruta que envíe.

> Nota de alcance: esto es una observación de ingeniería sobre lo que hace el código, no una
> opinión jurídica.

---

## 3. Barreras que sí se verificaron y siguen en pie

- La aplicación **se niega a arrancar** en modo real sin una referencia de autorización legal.
- El aislamiento entre propietarios se sostiene: 27 comprobaciones lo verifican, y un
  identificador ajeno devuelve 404 y nunca 403.
- Las fotos de tickets se re-codifican al subirlas y pierden el EXIF, **incluidas las
  coordenadas GPS**; se sirven por una ruta que verifica permisos.
- Los pagos siguen apagados: toda la ruta devuelve 501 de forma incondicional.
- Existe registro de auditoría de accesos y acciones sensibles.

---

## 4. Bloqueadores

### 4.1 El sitio público sigue pidiendo datos sin aviso — ABIERTO desde el 2026-08-11

Sin cambios. El formulario pide nombre, correo y teléfono; las páginas de aviso de privacidad y
términos siguen diciendo que el texto se publicará «muy pronto». **Lo desbloquea el texto de
Legal.**

### 4.2 La bitácora existe y nadie puede leerla

Verificado: `security.audit()` escribe en la tabla `audit_log`, y **ninguna pantalla la muestra**.
Hoy eso es teórico. Con clientes reales deja de serlo: personal de Aura con rol de administrador
puede leer datos de inquilinos de cualquier cuenta, y el rastro de que lo hizo no es consultable
por nadie. Ver D-029.

### 4.3 Sigue faltando la firma para operar con datos reales

Sin ella la plataforma no sale del modo simulación. No es una avería: funciona como se diseñó.

---

## 5. Decisiones que esperan al CEO

Tres del lote de la Fase 2.1 caen en el terreno de Legal. Están completas, con opciones y
recomendación, en `docs/phase2.1/DECISIONES_PENDIENTES.md`:

**5.1 (D-025) El paquete que se entrega al contador.** Es el objeto con más riesgo de fuga de
todo el sistema: sale de la plataforma y llega a un tercero que nunca aceptó el aviso de
privacidad. ¿Puede incluir fotos del interior de la vivienda de los inquilinos?
- **Recomendación:** que la casilla exista pero nazca **siempre desmarcada**, con pantalla de
  confirmación y registro de cada activación. Se descarta sin discusión incluirlas por defecto.

**5.2 (D-026) Retención.** ¿Cuántos años se conservan los comprobantes fiscales y cuánto duran
los paquetes generados?
- **Recomendación:** 7 años tras el cierre del ejercicio (cubre los 5 del SAT y los 3 a 7 del
  IRS); paquetes purgados a los 90 días, siempre regenerables. **El número exacto lo tiene que
  fijar Legal**, no ingeniería: una purga mal ajustada borra evidencia irrecuperable.

**5.3 (D-027) Descargo del módulo fiscal.** Texto propuesto: *«Aura registra y organiza sus datos
de gastos; no da asesoría fiscal, no calcula impuestos, no determina qué es deducible, no valida
ni timbra CFDI y no presenta ninguna declaración; el etiquetado SAT / IRS Schedule E es
orientativo.»*
- **Recomendación:** aprobarlo como borrador y someterlo a revisión de abogado titulado antes de
  publicar. Va en la pantalla del año fiscal y dentro del paquete exportado.

---

## 6. Próximos pasos

1. Entregar el aviso de privacidad y los términos del sitio público. Publicarlos es cuestión de
   minutos una vez redactados.
2. Fijar el plazo de retención de 5.2 por escrito.
3. Revisar el descargo de 5.3.
4. Cuando Legal firme, el CEO confirma **por separado y de forma explícita** el paso a datos
   reales. La firma de Legal por sí sola no lo activa.

---

## 7. Costo

Sin impacto directo. La revisión del descargo por un abogado titulado sí lo tendría y no está
presupuestada.
