# Diseño — Reporte de estado

**Fecha:** 2026-09-08
**Periodo:** requisitos de interfaz de la Fase 2.1
**Archivado en:** Aura/Reports/Design/

---

## 1. Resumen

**En riesgo, por una deuda que ya existía.** La Fase 2.1 añade siete pantallas nuevas a la
plataforma. Al inventariar los componentes disponibles apareció un problema anterior a este
lote: **nueve clases de CSS que las plantillas actuales usan no existen en la hoja de estilos.**
No fallan de forma visible — simplemente no aplican estilo — así que llevan tiempo ahí sin que
nadie las note.

Además, la plataforma y el sitio público **no comparten sistema visual**, y la plataforma es la
que se le va a enseñar a los clientes del SaaS.

---

## 2. Deuda detectada

### 2.1 Clases citadas que no existen

`.btn-danger` · `.flash-ok` · `.filters` · `.actions` · `.section-head` · `.btn-block` ·
`.alert-warning` · `.meta` · `.row-urgent`

Tres de ellas importan más que las otras: `.btn-danger` viste acciones destructivas (eliminar una
propiedad, terminar un arrendamiento) que hoy se muestran igual que cualquier otro botón; y
`.filters` es justamente la que necesitan los filtros del punto 2.2.

**Regla para la Fase 2.1:** ninguna plantilla nueva puede citar una clase que no esté en
`platform.css`. Las que falten se añaden en el mismo cambio.

### 2.2 La plataforma no sigue el sistema de marca

| Token | Sitio público | Plataforma |
|---|---|---|
| Tinta | `#14212B` | `#1F2724` |
| Borde | `#E4DDCF` | `#E1DACB` |
| Turquesa de acento | `#2CB1BC` | no existe |
| Coral de botón | `#C0492B` | no existe |
| Radios | 13–18 px | 6–10 px |
| Tipografía | Fraunces + Inter | del sistema |

La hoja de estilos declara por escrito que no busca igualar al sitio. Esa decisión era razonable
cuando la plataforma era una herramienta interna del CEO. **Con el pivote a SaaS deja de serlo:**
la plataforma es el producto que se vende, y hoy no se parece a la marca.

---

## 3. Componentes que faltan para la Fase 2.1

| Pantalla | Componente nuevo | Restricción que condiciona el diseño |
|---|---|---|
| Panel del propietario | Fichas de indicador (4 primarias + 4 secundarias) y bloque «Datos por revisar» | Debe leerse en teléfono; el menú lateral ya colapsa a 860 px |
| Filtros | Barra de filtros con recuento de resultados | **`.filters` no existe**; sin JS en línea |
| Gastos | Tabla con totales, y captura con comprobante | Tablas sin comportamiento adaptable hoy |
| Proveedores | Fichas o tabla con crear, editar y eliminar | Confirmación de borrado sin código en línea |
| Ticket resuelto | Zona de subida de fotos y documentos | El formulario actual **no acepta archivos**: hay que rediseñarlo |
| Cámara en móvil | Botón de captura | Se resuelve con un atributo del propio HTML, **sin JavaScript** |
| Ver contraseña | Botón dentro del campo | Área táctil ≥44 px; no debe romper el gestor de contraseñas |

### 3.1 Dos restricciones que no son negociables

**No se admite JavaScript ni CSS en línea.** La política de contenido lo prohíbe y hay una prueba
automática que falla si aparece `onclick=` o `style=` en el HTML. Todo comportamiento vive en un
único archivo de JavaScript. Esto ya causó un fallo real en el pasado: mientras hubo
confirmaciones en línea, **las acciones destructivas se ejecutaban sin preguntar**.

**La cámara está bloqueada por cabecera.** El diseño recomienda la vía de costo cero: un atributo
del campo de archivo que abre la cámara nativa del teléfono. Una cámara dentro de la página
obligaría a relajar esa cabecera y la política de contenido.

---

## 4. Bloqueadores

Ninguno propio. El diseño de interfaz está especificado en los cinco documentos de área y no
espera decisiones de Diseño.

---

## 5. Decisiones que esperan al CEO

**5.1 ¿Se alinea la plataforma con el sistema visual del sitio?**
- A: Alinear solo colores y radios. Trabajo moderado, sin costo de rendimiento.
- B: Alinear también la tipografía (Fraunces e Inter). Obliga a auto-hospedar 100–200 KB de
  fuentes por la política de contenido, en una aplicación pensada para el teléfono.
- C: Dejarlo como está.
- **Recomendación: A**, y hacerlo **antes** de construir las siete pantallas nuevas: alinear seis
  variables de color ahora cuesta una tarde; hacerlo después de duplicar el número de pantallas,
  bastante más. La B se puede evaluar cuando haya un cliente real mirando.

**5.2 ¿Se añaden las nueve clases que faltan como parte del lote?**
- **Recomendación: sí.** Tres de ellas visten acciones destructivas y filtros que la Fase 2.1
  necesita de todos modos.

---

## 6. Próximos pasos

1. Añadir las nueve clases ausentes a la hoja de estilos.
2. Decidir 5.1 antes de que empiece E11.
3. Especificar las fichas de indicador y la barra de filtros con el sistema ya alineado.

---

## 7. Costo

Sin impacto. Las fuentes de la opción B serían auto-hospedadas y gratuitas; su costo es de peso
de página, no de dinero.
