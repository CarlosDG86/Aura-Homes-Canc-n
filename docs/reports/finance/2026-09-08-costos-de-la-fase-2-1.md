# Finanzas — Reporte de estado

**Fecha:** 2026-09-08
**Periodo:** implicaciones económicas de la Fase 2.1
**Archivado en:** Aura/Reports/Finance/

---

## 1. Resumen

**En marcha.** El costo recurrente sigue siendo **0 USD** y no se ha comprometido ningún método
de pago. La Fase 2.1 no cambia eso por sí sola, pero pone sobre la mesa el **primer cargo
recurrente inevitable** del proyecto: el correo de producción, sin el cual una de las funciones
que pidió el CEO no puede existir.

Hay además una decisión de modelo de negocio que Finanzas debería revisar antes de que se
construya: **tal y como está escrito el punto 7.2, un cliente de 25 casas tendría menos funciones
que uno de 5.**

---

## 2. Costo actual

| Concepto | Proveedor | Mensual |
|---|---|---|
| Sitio público | Cloudflare | 0 USD |
| Plataforma | Fly (suspendida) | 0 USD |
| Respaldos | cancelados por el CEO | 0 USD |
| Repositorio | GitHub | 0 USD |
| **Total** | | **0 USD** |

---

## 3. Lo que la Fase 2.1 añadiría

| Concepto | Cuándo | Mensual estimado |
|---|---|---|
| Correo de producción con dominio propio (D-023) | **Bloquea el punto 3.2** | 0–6 USD |
| Dominio propio `aurahomescancun.com` | Pendiente desde agosto | ~1 USD |
| Hospedaje de la plataforma, si vuelve a estar en línea | Después de E9 | por determinar |
| Agente de IA (sigue desconectado) | Solo si se aprueba | 1–2 USD |
| Servicio de correo entrante para el punto 7.4 | Solo si se aprueba (D-028) | por cotizar |

**El correo de producción es el único que no es opcional** si se quiere el punto 3.2. Los demás
siguen siendo decisiones abiertas.

---

## 4. Bloqueadores

Ninguno de índole financiera. Nada de lo anterior está contratado.

---

## 5. Decisiones que esperan al CEO

**5.1 (D-018) La matriz de planes tiene una asimetría que conviene revisar antes de construirla.**

Tal como está escrito el punto 7.2:

| Plan | Incluye |
|---|---|
| Standard | multi-propiedad |
| Standard+ | + agente de WhatsApp y correo |
| Enterprise | +20 casas |
| Enterprise+ | + agente, tabla de proveedores y cotización automática |

Leído literalmente, **Enterprise (25 casas) no incluye el agente, y Standard+ (5 casas) sí**.
Un cliente que crece de 15 a 25 casas perdería funciones al subir de plan.

- A: El «+» significa siempre «agente», y el nombre base significa escala. Enterprise incluye
  todo lo de Standard+ más el volumen.
- B: Lectura literal, asumiendo la asimetría.
- **Recomendación: A.**

**5.2 (D-018/D-019) ¿Qué se cobra y qué es gratis?**

- A: Directorio de proveedores, captura de gastos y exportación fiscal **manual** en todos los
  planes, incluido el de prueba; lo que se cobra es la **automatización**.
- B: Lectura literal del 7.2: proveedores y desglose fiscal solo en los planes «+».
- **Recomendación: A.** Retener los registros fiscales de un cliente detrás de un muro de pago es
  frágil: el dato entra incompleto once meses y en marzo, con la auditoría encima, el cliente
  descubre que no puede sacar nada. Lo que se vende bien es ahorrar trabajo, no rescatar datos.

**5.3 (D-019) Prueba gratuita y precio: 90 días para una casa frente a los 60 días para
«clientes fundadores» a $2,500 MXN/mes de D-010.**

Verificado: ni «60 días», ni «fundador», ni «2,500» aparecen en ningún archivo del repositorio.
D-010 vive solo en Drive, así que **otros departamentos lo seguirán citando hasta que se retire
por escrito**.

- **Recomendación:** 90 días para una casa como regla única; un «fundador» pasa a ser una cuenta
  con duración de prueba distinta escrita a mano y una nota que explique por qué. Dos regímenes
  automáticos son dos reglas de vencimiento y dos avisos para una promoción que hoy no usa nadie.

**5.4 (D-028) El tope de gasto del agente de IA es hoy global.**

Verificado: el límite mensual suma **todas** las filas de consumo sin filtrar por cuenta. En
cuanto haya un segundo cliente, el primero que use cotización automática deja sin presupuesto a
todos los demás.

- **Recomendación:** tope por cuenta ligado al plan, antes del segundo cliente real. No es
  urgente mientras el agente siga desconectado.

---

## 6. Próximos pasos

1. Revisar 5.1 y 5.2 — son de modelo de negocio y condicionan qué se construye en E9 y E14.
2. Presupuestar el correo de producción: es la única partida que bloquea una función pedida.
3. Retirar por escrito la regla de los 60 días si 5.3 se aprueba.

---

## 7. Impacto presupuestal de esta entrega

Cero. No se contrató, activó ni comprometió nada.
