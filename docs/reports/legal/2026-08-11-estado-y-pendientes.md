# Legal — Reporte de estado

**Fecha:** 2026-08-11
**Periodo:** Publicación del sitio y de la plataforma
**Archivado en:** Aura/Reports/Legal/

---

## 1. Resumen

**En riesgo.** La plataforma de gestión está bien contenida: no puede operar con
datos reales de inquilinos hasta que Legal firme, y eso está impuesto por el
código, no por disciplina. **El sitio público sí tiene un hueco abierto:** pide
datos personales por formulario mientras su aviso de privacidad dice que "se
publicará muy pronto".

---

## 2. Completado

### 2.1 Barreras técnicas ya puestas

La plataforma opera en modo simulación. No es una convención: la aplicación
**se niega a arrancar** en modo real si no se le indica una referencia de
autorización legal.

- Solo acepta correos de dominios de prueba y teléfonos con formato de prueba.
- No envía correos reales.
- Los módulos de mayor riesgo están construidos pero apagados:
  - **2b — portal de inquilinos:** encendido solo para pruebas, sin datos reales.
  - **2c — pagos de renta:** construido y **apagado**. No procesa dinero.

### 2.2 Protecciones de datos personales ya implementadas

- Las fotos de los reportes de mantenimiento se **re-codifican al subirlas**,
  lo que borra el EXIF **incluidas las coordenadas GPS**. Publicar dónde vive un
  inquilino sería una fuga de datos personales.
- Las fotos se sirven por una ruta que verifica permisos, nunca como archivo
  público.
- Existe un registro de auditoría con accesos y acciones sensibles.
- Un propietario no puede ver datos de otro; verificado con pruebas
  automatizadas.
- Los respaldos se guardan cifrados con AES-256.

---

## 3. En curso

Nada. Todo lo que depende de ingeniería está hecho; lo que falta depende de
Legal.

---

## 4. Bloqueadores

### 4.1 El sitio recoge datos personales sin aviso de privacidad — ABIERTO HOY

La página de aviso de privacidad está publicada, pero su texto dice que el
documento "está en la fase final de redacción y se publicará muy pronto".
Lo mismo los términos.

Mientras tanto, el formulario de contacto pide **nombre, correo y teléfono**.
Es decir: hoy, en vivo, se solicitan datos personales sin el aviso que la
LFPDPPP exige.

> Nota de alcance: esto es una observación de ingeniería sobre lo que hay
> publicado, no una opinión jurídica. Corresponde a Legal determinar la
> exposición real y redactar el texto.

Lo desbloquea: el texto de Legal. Publicarlo es cuestión de minutos una vez
entregado.

### 4.2 Falta la firma para operar con datos reales

Sin ella, la plataforma no puede dejar el modo simulación. No es urgente en el
sentido de que nada está roto — está funcionando como se diseñó.

Se necesita:
- Aviso de privacidad y mecanismo de consentimiento validados (LFPDPPP).
- Criterio sobre cuánto tiempo se conservan las fotos de los reportes.
- Criterio sobre los documentos de pago de la fase 2c.

---

## 5. Decisiones que esperan al CEO

**5.1 Qué hacer mientras llega el texto legal.**

- A: Dejar el formulario como está.
- B: Retirar el formulario y dejar solo WhatsApp hasta tener el aviso.
- C: Añadir una nota breve y una casilla de consentimiento provisional.
- **Recomendación: C.** Es el equilibrio razonable: no se pierde el canal y se
  deja constancia de que se informó. B es la opción más conservadora si Legal
  lo prefiere.

**5.2 Datos reales en la base local.** La copia del equipo del CEO contiene a
una persona real con su correo. No está publicada, pero existe. Recomendación:
dejarla hasta que Legal firme; no ha salido del equipo del CEO.

---

## 6. Próximos pasos

1. Legal entrega el aviso de privacidad y los términos.
2. Se publican (minutos de trabajo).
3. Se decide 5.1 mientras tanto.
4. Cuando Legal firme, el CEO confirma **por separado y de forma explícita** el
   paso a datos reales. La firma de Legal por sí sola no lo activa.

---

## 7. Costo

Sin impacto. Ninguna de estas barreras cuesta dinero.
