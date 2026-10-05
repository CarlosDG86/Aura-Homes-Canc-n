# Legal — Reporte de estado

**Fecha:** 2026-10-04
**Periodo:** cierre de la construcción de la Fase 2.1 — qué dato sale ahora de la plataforma
**Archivado en:** Aura/Reports/Legal/

> Este documento es investigación interna, no asesoría. Requiere revisión de abogado mexicano
> titulado antes de usarse con clientes.

---

## 1. Resumen

**Bloqueado a la espera de Legal, como estaba previsto.** Todo lo construido en la Fase 2.1
—inquilinos, proveedores, comprobantes, gastos y ahora el paquete fiscal— funciona **solo en
modo de pruebas** detrás de la puerta `DATA_MODE`. Con datos reales la aplicación se niega a
arrancar sin una referencia documental de autorización legal.

Lo nuevo que Legal tiene que mirar es **una función que saca datos de la plataforma**: el
paquete fiscal que el propietario descarga y entrega a su contador.

---

## 2. Lo nuevo: una salida de datos, no una entrada

Hasta ahora todo lo revisado era **captura**. El paquete fiscal es lo contrario: un archivo ZIP
que sale del sistema y pasa a manos de un tercero (el contador del cliente) sobre el que Aura
no tiene ningún control.

**Lo que SÍ sale:** gastos, importes, categorías fiscales, proveedores, y de cada reporte de
mantenimiento el título, las fechas y la resolución escrita por el propietario.

**Lo que NO sale nunca:**

| Dato | Cómo se evita |
|---|---|
| Nombre del inquilino | Se sustituye por «Inquilino #\<número de contrato\>» |
| Correo del inquilino | No se incluye en ningún archivo |
| Teléfono del inquilino | No se incluye en ningún archivo |
| Descripción que escribió el inquilino | Se omite: es texto libre y ahí aparece de todo |
| Fotos del interior de la vivienda | **Excluidas por omisión** |

Las tres primeras tienen **prueba automatizada que busca esos valores en todos los archivos de
texto del paquete** y falla si aparecen.

### 2.1 Las fotos del interior

La casilla existe porque un auditor puede pedir evidencia de una reparación, pero:

- nace **desmarcada**;
- vive en una pantalla intermedia que no se puede saltar, con la advertencia de que muestran el
  interior de la vivienda de sus inquilinos;
- marcarla queda **en la fila del paquete y en la bitácora**, con una acción de nombre propio.

Eso último es deliberado: es la respuesta el día que un inquilino pregunte quién sacó fotos de
su casa y a quién se las dieron.

### 2.2 Sello de modo

Cada gasto guarda en qué modo nació. El paquete **excluye toda fila de otro modo** y declara
cuántas dejó fuera. Así una fila de pruebas no puede colarse en un paquete fiscal real ni
aunque alguien cruce las bases. En modo pruebas, el nombre del ZIP y el LEEME llevan la marca
`DATOS-DE-PRUEBA`.

---

## 3. Lo que Legal necesita decidir o firmar

| # | Asunto | Por qué importa |
|---|---|---|
| 1 | **Encargado de datos de terceros** bajo el modelo SaaS (D-010) | Bloqueante antes del primer contrato con otra administradora |
| 2 | **Texto del descargo fiscal** (D-027) | Está escrito y en pantalla, en cada reporte y en cada paquete. Dice que la plataforma registra y organiza, no calcula impuestos ni decide qué es deducible |
| 3 | **Retención** de comprobantes fiscales y fotos de tickets (D-026) | Hoy no hay borrado automático de nada |
| 4 | **Aviso de privacidad y términos** del sitio público | Las dos páginas siguen diciendo que el texto llegará pronto, mientras el formulario ya pide nombre, correo y teléfono |
| 5 | **Datos del proveedor** (persona física): nombre, celular, RFC | En pruebas, el RFC se rechaza y las notas libres rechazan correos y secuencias de diez dígitos |

### 3.1 Límite declarado, no disimulado

**No se puede validar el contenido de un PDF.** Un comprobante subido en modo pruebas puede
contener datos reales de un tercero. El control enforzable es la banda visible del modo y el
sello en cada fila, que permite purgar con exactitud los archivos de la época de pruebas. Queda
escrito como riesgo aceptado, no como problema resuelto.

---

## 4. Lo que NO se bloquea por cobro, a propósito

Decisión de producto con lectura legal: **la exportación fiscal y la descarga de documentos
siguen funcionando con la prueba vencida y con la cuenta suspendida o cerrada.**

Retener los registros fiscales de un cliente tras un muro de pago es frágil comercialmente y
discutible en portabilidad de datos bajo la LFPDPPP. Si un cliente no puede entregarle a su
contador lo que le pide el SAT porque dejó de pagarnos, el obstáculo somos nosotros.

---

## 5. Próximos pasos

- Revisión del texto del descargo por abogado titulado.
- Definir plazos de retención (D-026) para poder construir el borrado.
- Texto de aviso de privacidad y términos para el sitio público.

---

## 6. Costo

Cero. La única partida previsible es la revisión del abogado, que no se ha cotizado.
