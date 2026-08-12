# Diseño — Reporte de estado

**Fecha:** 2026-08-11
**Periodo:** Rediseño de cabecera y optimización de marca
**Archivado en:** Aura/Reports/Design/

---

## 1. Resumen

**En marcha.** La cabecera pasó de ocupar un tercio de la pantalla del teléfono
a 60 px, y el logo de 1.5 MB a 39 KB. Queda una edición a medias en el CSS del
equipo del CEO que dejaría el logo invisible si se publica tal cual.

---

## 2. Completado

### 2.1 Cabecera

| | Antes | Ahora |
|---|---|---|
| Alto en móvil | 216 px | **60 px** |
| Alto en escritorio | 216 px | **76 px** |
| Alto del logo | 200 px | 46 px móvil / 58 px escritorio |
| Fondo | Arena `#F7F3EC` | **Arena muy clara `#FDFBF6`** |

El valor de 216 px era el mismo en teléfono y en monitor: no había regla
adaptable. En un teléfono típico eso significaba que el visitante veía cabecera
y nada más hasta que hacía scroll — en un sitio cuyo criterio de diseño es
"mobile-first" y cuyos usuarios llegan casi todos por celular.

El nuevo fondo se separa del fondo de la página sin salirse de la paleta
"Caribe Cálido" que ya usa el sitio.

### 2.2 Marca

El PNG venía a 1024×1024 con **40 % de margen transparente**: el logo ocupaba
poco más de la mitad del lienzo. Se recortó a la marca y se sirve a 180×224,
cuatro veces el tamaño en que se muestra, para que se vea nítido en pantallas
de alta densidad.

Resultado: **1476 KB → 39 KB**, sin pérdida visible. A su peso anterior, el
logo por sí solo comprometía el objetivo de rendimiento del plan.

El original de 1024 px se conservó fuera del repositorio, en `assets-src/`.

### 2.3 Sistema de diseño

Sin cambios. Sigue vigente: tipografías Fraunces (títulos) e Inter (texto),
paleta teal/turquesa/coral sobre arena, tarjetas de radio 18 px.

---

## 3. En curso

Prueba de variantes de logo en el equipo del CEO. Hay tres archivos conviviendo:
`logo.png` (el que se usa), `logo1.png` y `logoold.png`.

---

## 4. Bloqueadores

### 4.1 Regla de CSS a medio editar

En la copia del CEO, `.brand-logo` quedó con `height:1px`, lo que hace el logo
**invisible**. La versión publicada está bien; el riesgo es publicar esa copia
tal cual.

Corrección sugerida con el logo actual (180×155, sin la línea de leyenda):
46 px en móvil y 58 px en escritorio.

### 4.2 Dos fichas con imágenes de relleno

"Casa en Residencial Cumbres" y "Departamento SM 15" muestran rectángulos
grises de marcador de posición, en vivo. Se ven inacabadas junto a las demás.
Es la misma decisión que plantea el reporte de Marketing (§5.1).

---

## 5. Decisiones que esperan al CEO

**5.1 Cuál de los tres logos es el definitivo.**

- El actual (180×155) no lleva la línea "CASAS EN RENTA Y ADMINISTRACIÓN" y
  está mejor proporcionado para una cabecera horizontal.
- El anterior la incluía, pero a 46 px de alto esa línea es ilegible.
- **Recomendación:** el actual, y reservar el que lleva la leyenda para
  materiales impresos o firmas de correo, donde sí se lee.

**5.2 Limpiar los archivos sobrantes.** Decidir si `logo1.png` y `logoold.png`
se conservan o se retiran, para no arrastrar tres versiones.

---

## 6. Próximos pasos

1. Cerrar 5.1 y corregir la regla de 1 px.
2. Medir Lighthouse en móvil — **aún no se ha medido**. La cabecera y el logo
   eran los dos frenos evidentes; ya no lo son, pero eso hay que comprobarlo.
3. Revisar el resto de imágenes: `banner.jpg` pesa 280 KB y las fotos de las
   fichas rondan 50–85 KB cada una.

---

## 7. Costo

Sin impacto.
