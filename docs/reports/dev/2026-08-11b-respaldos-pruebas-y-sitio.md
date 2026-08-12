# Desarrollo e Infraestructura — Reporte de estado (2)

**Fecha:** 2026-08-11
**Periodo:** Posterior al reporte "Phase 2 en producción" del mismo día
**Archivado en:** Aura/Reports/Development/

> Complementa al reporte anterior; no lo sustituye. Aquel cerraba la
> construcción de la fase 2; este cubre lo hecho después.

---

## 1. Resumen

**En marcha.** Se cerró la decisión 5.1 del reporte anterior: ya hay respaldos
automáticos verificados. Se publicaron los cambios de diseño y contenido del
sitio. Y se corrigió un problema serio que apareció al revisar: **las pruebas
automatizadas no estaban en el repositorio**.

---

## 2. Completado

### 2.1 Respaldos automáticos (decisión 5.1 — cerrada)

Cada noche a las 02:00 de Cancún: instantánea de ambas bases más todas las
fotos de reportes, cifrada con AES-256 y guardada 90 días. Costo: 0 USD.

Dos decisiones que marcan la diferencia entre esto y un respaldo de adorno:

- **Se verifica antes de cifrarse.** Se descarga, se abre la base, se corre
  `integrity_check` y se contrastan los conteos de filas contra el manifiesto.
  Comprobado que detecta los tres modos de fallo: base corrompida, foto ausente
  y base ausente. Un verificador que solo se ha visto pasar no prueba nada.
- **Instantánea, no copia de archivo.** Copiar la base mientras la aplicación
  escribe puede capturar una transacción a medias y producir un archivo corrupto
  que *parece* un respaldo válido. Se usa la API de respaldo de SQLite, que es
  coherente con la aplicación en marcha.

También se escribe fuera del volumen: llenar el disco de 1 GB con respaldos
tumbaría justo lo que el respaldo protege.

**Falta un paso del CEO:** cargar dos secretos en el repositorio. Detalle en
`docs/phase2/BACKUP.md` §2. Sin ellos el respaldo falla al primer paso diciendo
exactamente cuál falta.

> ⚠️ La frase de cifrado **no tiene recuperación**. Si se pierde, los respaldos
> quedan ilegibles para siempre. Es el único dato del sistema que no se puede
> regenerar.

### 2.2 Sitio público

- Cabecera de 216 px a 60/76 px, fondo arena claro.
- Logo de 1476 KB a 39 KB.
- Eliminada la propiedad de prueba `aur-test1` (decisión 5.4 del reporte
  anterior — cerrada).
- Cuatro fichas de prueba nuevas con textos ES/EN.
- Retirada una foto de la galería de La Rioja cuyo archivo ya no existía: se
  habría publicado una imagen rota.

Publicado y verificado contra la dirección real, no solo en local.

### 2.3 Pruebas automatizadas

Ver §4 — este punto es un hallazgo, no un logro.

---

## 3. En curso

Ediciones de logo y cabecera en el equipo del CEO, sin publicar.

---

## 4. Hallazgo: las pruebas no estaban en el repositorio

El reporte anterior afirma "237 pruebas automatizadas en verde". Era cierto
cuando se ejecutaron, pero **los archivos vivían en una carpeta temporal de
sesión**: sin versionar, sin ejecutarse en el flujo automático, y destinados a
borrarse. Nadie habría podido volver a correrlas.

Lo hecho: se movieron a `platform/tests/`, se cambió una ruta fija de Windows
por una relativa para que corran también en Linux, y se conectaron al flujo de
despliegue. Ahora una prueba en rojo impide publicar.

Al conectarlas aparecieron cuatro fallos. **Ninguno era del producto:**

- Una suite no importaba un módulo que usaba.
- Otra es anterior al segundo factor obligatorio: su inicio de sesión no
  completaba el código, así que el administrador quedaba a medias y la ruta
  redirigía antes de revocar las sesiones. Se verificó por separado que la
  conducta real **sí** revoca y expulsa al usuario.

Ese segundo caso merece atención: la prueba comprobaba que la respuesta fuera
un redirección, y el camino de rechazo **también** devuelve una redirección.
Pasaba por el motivo equivocado. Queda anotado en el código.

**Resultado: 261 comprobaciones en verde**, validadas en un entorno limpio con
solo las dependencias declaradas — la misma disposición que usa el flujo
automático. Esa comprobación existe precisamente porque uno de los tres fallos
del primer despliegue fue una dependencia instalada a mano y nunca declarada.

---

## 5. Decisiones que esperan al CEO

**5.1 Cargar los dos secretos del respaldo.** Hasta entonces el respaldo
existe pero no corre. Es el pendiente más importante de este reporte.

**5.2 Regla de CSS a medio editar.** En la copia del CEO, el logo quedó con
altura de 1 píxel: sería invisible. La versión publicada está bien. Ver reporte
de Diseño §4.1.

**5.3 Copia de trabajo desincronizada.** El archivo del flujo de despliegue en
el equipo del CEO perdió el paso que ejecuta las pruebas. La versión publicada
sí lo tiene. Si se publica esa copia tal cual, ese paso desaparecería.

---

## 6. Próximos pasos

1. Cargar los secretos del respaldo y lanzarlo una vez a mano para comprobarlo.
2. Probar el segundo factor en producción con el teléfono a mano y **guardar la
   clave de respaldo**. Sigue siendo lo único no ejercitado en producción.
3. Medir Lighthouse en móvil. **Nunca se ha medido**; el criterio de 90+ del
   plan sigue sin comprobarse, aunque se hayan quitado los dos frenos evidentes.
4. Visto bueno de QA.

---

## 7. Costo

Sin cambios: **0 USD al mes**. Los respaldos entran en la capa gratuita.

---

## 8. Nota de transparencia

Dos cosas que conviene registrar de este periodo:

- El reporte anterior, ya archivado en Drive, afirma que hay 237 pruebas. El
  número era correcto; el problema era **dónde estaban**. Hoy son 261 y están
  versionadas.
- La herramienta usada para fusionar el grafo de conocimiento documenta que
  guarda el resultado, y no lo hace: solo lo devuelve. La primera fusión
  reportó éxito con 773 nodos mientras el archivo en disco seguía con 433. Se
  detectó al comparar contra el respaldo previo. No se perdió nada, pero es el
  patrón que más veces ha aparecido en este proyecto: **un paso reporta éxito y
  el siguiente trabaja sobre datos que no cambiaron.**
