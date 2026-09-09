# Decisiones que esperan al CEO — Fase 2.1

**Fecha:** 2026-09-08 · **Origen:** consolidación de las 53 decisiones que plantearon los
cinco diseños de área, fundidas y ordenadas por urgencia.

> **Ya cerradas y fuera de discusión:** D-013 (la cuenta es la raíz de aislamiento),
> D-014 (español con cadenas extraídas), D-015 (la vista de auditores es una exportación),
> D-016 (gastos y proveedores bajo la puerta legal existente).

---

## Bloquean la construcción

Sin estas respuestas, la etapa indicada no se puede escribir.

### D-017 · Cierre del punto 7.4: su texto se corta en «Si el owner aprueba…». ¿Qué debe ocurrir exactamente cuando el propietario aprueba una cotización?

**Bloquea:** E14

**Por qué importa.** Es lo único que impide cerrar la máquina de estados de cotizaciones y, con ella, la etapa E14 y el diferencial del plan Enterprise+. Mientras siga abierta, aprobar solo sella el estado y no notifica, no agenda, no cambia el ticket y no crea ningún pagadero. Aviso: el diseño de proveedores ya se tomó una libertad marcada como [supuesto] — aprobar asigna el proveedor al ticket si estaba vacío. Si eso no es lo que usted quiere, dígalo.

**Opciones:**

1. Solo se registra: el propietario llama él mismo al proveedor (es lo único que se construye hoy)
2. La plataforma envía la orden de trabajo al proveedor por correo o WhatsApp
3. Se agenda una visita (la tabla `visits` existe vacía, models.py:502)
4. Se crea automáticamente un gasto estimado y el ticket pasa a «en proceso»
5. Hay un monto por debajo del cual se auto-aprueba sin que nadie toque nada

**Recomendación.** Escriba la frase completa antes de que empiece E14. No se va a inventar: `ticket_quotes.status` se guarda como texto validado y no como Enum precisamente para que ampliar la máquina de estados después no exija tocar la base. Hasta entonces, aprobar no le escribe a nadie.

---

### D-018 · Confirme la matriz de planes en UNA sola tabla: qué incluye cada plan, el límite exacto de propiedades, y qué es gratis frente a qué se cobra.

**Bloquea:** E9 y E14

**Por qué importa.** Cinco preguntas distintas que en realidad son una, y hoy las cinco están abiertas: (a) el límite de 20 propiedades para Standard/Standard+ es un supuesto mío; (b) tal como usted lo escribió, Standard+ incluye el agente pero Enterprise no, así que un cliente de 25 casas tendría menos funciones que uno de 5; (c) su punto 5 pide la lista de proveedores «para el owner» sin condición pero su 7.2 la mete en Enterprise+; (d) su 7.3 se lee como que el desglose fiscal es solo de los planes «+», mientras que D-015 lo define como algo que el propietario descarga; (e) hay que dejar escrito que entrar y recuperar la contraseña no se cobran nunca.

**Opciones:**

1. Directorio de proveedores, captura de gastos y exportación fiscal MANUAL en todos los planes, incluido el trial; lo que se cobra es la AUTOMATIZACIÓN (agente, cotización automática, paquete anual precalculado, gastos recurrentes)
2. Lectura literal del 7.2: proveedores y desglose fiscal solo en los planes «+»
3. El «+» significa siempre «agente» y el nombre base significa escala, con la asimetría asumida
4. Enterprise incluye todo lo de Standard+ más la escala

**Recomendación.** Opción 1 más «el + es siempre el agente». Retener los registros fiscales de un cliente detrás de un muro de pago es frágil comercialmente (el dato entra incompleto once meses y en marzo, con la auditoría encima, descubre que no puede sacar nada) y discutible en portabilidad bajo LFPDPPP. Pero necesito que confirme el 20 y que zanje la asimetría: son dos celdas de una tabla en `plans.py`, ni esquema ni migración.

---

### D-019 · Prueba gratuita y precio: los 90 días para una casa de su feedback frente a los 60 días para «clientes fundadores» a $2,500 MXN/mes de D-010. ¿Lo nuevo sustituye a lo anterior?

**Bloquea:** E9

**Por qué importa.** Verifiqué el repositorio entero: ni «60 días», ni «fundador», ni «2,500» aparecen en ningún archivo — D-010 vive solo en Drive, así que otro departamento lo seguirá citando hasta que usted lo retire por escrito. Y necesito saber si el precio entra en el producto: cualquier importe dentro de la plataforma es el primer ladrillo de facturación, y la facturación cae bajo la puerta legal de pagos que hoy cierra un 501 incondicional.

**Opciones:**

1. 90 días para una casa, para todos; un «fundador» es una cuenta con `trial_days = 60` escrito a mano y una nota que dice por qué; el precio vive en el sitio público y en el documento comercial, nunca en la base
2. Conservar los 60 días como segundo régimen automático, con su bandera y su camino de código
3. El precio entra como texto informativo en la pantalla «Mi cuenta»
4. El precio entra como importe por plan, con vencimiento y estado de pago

**Recomendación.** La primera. Dos regímenes de prueba son dos estados, dos reglas de vencimiento y dos avisos para una promoción que hoy no usa nadie. Confirme también el tope de extensión de prueba (+180 días sobre la fecha de inicio) para que un error de tecleo no genere una prueba de veinte años.

---

### D-020 · Migración de sus dos propietarios actuales (propietario #2 con 2 casas, propietario #3 con 1): una cuenta cada uno, con plan sin límite y sin reloj de prueba. ¿Alguno de los dos es en realidad un cliente y no usted?

**Bloquea:** E9 (irreversible en la práctica)

**Por qué importa.** Es irreversible en la práctica: fusionar dos propietarios en una cuenta y descubrir después que uno era un cliente es una fuga entre clientes. Y hay una consecuencia concreta que necesita su visto bueno: las tres propiedades reales tienen `site_ref`, o sea vinieron de la sincronización del sitio público. Si la migración no marca esas dos cuentas como «operadoras», la siguiente sincronización DEJA DE PUBLICAR sus tres casas el primer día.

**Opciones:**

1. Una cuenta cada uno, plan sin límite, marcadas «plan sin asignar» hasta que usted decida, y ambas como cuentas operadoras
2. Una sola cuenta para los dos, si en realidad ambos son usted
3. Cuentas separadas pero en prueba, para probar el flujo real de trial

**Recomendación.** La primera, y dígamelo ANTES de la migración si alguno debe entrar en prueba. Les doy plan sin límite a propósito: dejarlos en trial (límite 1 casa) los pondría por encima del límite el día uno y usted viviría su propia plataforma como una avería. Separar o fusionar después es un POST auditado y barato; deshacer una fusión, no.

---

### D-021 · Punto 6.1: «una vez resuelto el ticket, el owner puede agregar tickets o documentos». ¿«tickets» fue un lapsus por «fotos y comprobantes», o quiere encadenar un ticket de seguimiento a uno resuelto?

**Bloquea:** E12

**Por qué importa.** Tres áreas lo leyeron como lapsus y diseñaron fotos y comprobantes. Si era literal, no hay NADA construido: verifiqué que ninguna ruta permite hoy al propietario crear un ticket de ninguna clase — solo los crea el inquilino. Serían una columna `parent_ticket_id`, una ruta y una pantalla, y no están en ninguna etapa.

**Opciones:**

1. Era «fotos y comprobantes» — es lo que se ha diseñado
2. Es literal: quiero encadenar un ticket derivado a uno resuelto (el plomero volvió, la fuga reapareció)

**Recomendación.** Confirme la primera, que encaja con su 6.2 («tomar fotos… al cerrarlos el owner»). Si era la segunda, dígalo ahora: añadirla después es barato, pero descubrirlo en la demo no lo es.

---

### D-022 · El administrador queda FUERA de la recuperación por correo (usted escribió «send a reset to owner and user role»). ¿Cuál es entonces su vía de emergencia, y tiene acceso de consola a la máquina?

**Bloquea:** E10

**Por qué importa.** Publicar un formulario que acepte el correo del administrador re-expondría por la puerta principal justo la cuenta que la URL oculta y el TOTP intentan proteger, y reduciría toda esa cadena a «quien controle el buzón». Pero sin elegir una vía, la cuenta que lo ve todo se queda sin salida. Aviso: el guion de consola que resolvía esto se cayó de la etapa de acceso y hay que devolverlo.

**Opciones:**

1. Guion de consola en el servidor (`platform/scripts/restablecer_admin.py`), con opción para reiniciar también el TOTP cuando lo que se pierda sea el teléfono
2. Una segunda cuenta de administrador con su propio TOTP, guardada aparte
3. Permitirle la recuperación por correo exigiendo además el código TOTP en el mismo formulario

**Recomendación.** La primera, y confírmeme que tiene acceso de consola a la máquina — la fase local en curso lo respalda, pero es un supuesto mío. Perder el teléfono y perder la contraseña son dos averías distintas y el guion debe cubrir las dos.

---

### D-023 · Correo saliente de producción: qué buzón y qué dominio envían, y quién configura SPF y DKIM.

**Bloquea:** E10 (dependencia externa)

**Por qué importa.** Es la ÚNICA dependencia externa de todo el lote, y sin ella su punto 3.2 queda escrito e inservible en real: sin SPF y DKIM el correo cae en no deseados, el propietario cree que la plataforma está rota, agota su límite de 3 intentos por hora y acaba llamándole a usted — que es exactamente el trabajo que este flujo venía a quitarle. Mientras no exista, el diseño oculta el enlace y la ruta devuelve 404.

**Opciones:**

1. Buzón no-responder@ en el dominio de Aura Homes, con Google Workspace o Zoho, y SPF/DKIM configurados por Infra
2. Reutilizar su buzón personal como remitente
3. No configurar SMTP por ahora y dejar la recuperación oculta

**Recomendación.** La primera. La segunda se descarta: un remitente personal en un correo transaccional daña su reputación de envío y expone su dirección. Esto hay que abrirlo con Infra ya, porque el plazo de aprovisionamiento de un dominio de correo no lo controla Desarrollo.

---

### D-024 · Antes de enseñar el panel: ¿se cargan los contratos de arrendamiento de sus casas rentadas, y se añaden fecha de inicio, fecha de fin y renta mensual al alta de inquilino?

**Bloquea:** E11 y E13

**Por qué importa.** Verificado en su base: 3 propiedades y 0 arrendamientos, con una casa marcada como «rentada» en el sitio público. El primer día su panel dirá Ocupación 0 %. El número no está mal — los contratos no están cargados. Y hay algo peor: el alta de inquilino de hoy crea el contrato SIN fechas ni renta, así que tres indicadores («contratos por vencer», «renta contratada», «antigüedad») quedarán en «sin datos» para siempre, y el libro fiscal saldrá sin ingresos. Esos tres campos existen en la base y nunca se escriben. Ninguna de las cinco áreas se los adjudicó.

**Opciones:**

1. Cargar los 2-3 contratos y añadir los tres campos al formulario que ya existe
2. Arrancar con el estado vacío explícito («sin arrendamientos registrados») y cargarlos sobre la marcha
3. No añadir los campos por ahora

**Recomendación.** Las dos cosas, y es la decisión con más impacto por unidad de esfuerzo de todo el lote: son tres campos en un formulario existente y 2-3 altas. Sin ellas, el panel del punto 2.1 y la exportación fiscal del 2.3 se entregan honestos y vacíos, y ese es el momento en que un panel pierde la confianza de quien lo abre por primera vez.

---

## Antes de operar con datos reales

No frenan la construcción, pero sí el paso a datos reales de inquilinos o proveedores.

### D-025 · Datos personales de terceros: (a) ¿el paquete que entrega a su contador puede incluir fotos del interior de la vivienda de sus inquilinos? (b) confirmo que ningún reporte descargable lleva nombre, correo ni teléfono de inquilino; (c) los proveedores quedan bajo el mismo candado de pruebas que los inquilinos; (d) como comprobante solo se aceptan imagen, PDF y XML.

**Por qué importa.** El paquete descargado es el objeto con más riesgo de fuga de todo el sistema: sale de la plataforma y llega a un tercero (el contador) que nunca aceptó su aviso de privacidad, y lo que usted haga con el ZIP después no lo puede mitigar el código. Sobre (c): mientras Legal no firme, usted NO podrá teclear el teléfono real de su plomero — verá el mismo error que ya sale al dar de alta un inquilino real. Un plomero autónomo es una persona física y su celular es dato personal de un tercero que no aceptó nada. Sobre (d): Word, Excel y ZIP quedan fuera a propósito porque son vectores de macro y no hay forma de sanearlos.

**Opciones:**

1. Casilla de fotos que existe, nace SIEMPRE desmarcada, con pantalla intermedia de confirmación y registro de cada activación
2. La casilla no existe: el paquete lleva solo comprobantes, CSV y texto
3. Fotos incluidas por defecto, con opción de excluirlas

**Recomendación.** La primera para las fotos; confirmar (b), (c) y (d) tal como están. La tercera opción queda descartada sin discusión. Y si su contador exige Word o Excel, hay que decidirlo AHORA, no al construir la exportación.

---

### D-026 · Retención y topes: ¿cuántos años se conservan los comprobantes, cuánto duran los paquetes ZIP generados, y bastan 10 fotos y 5 documentos por ticket para respaldar una auditoría del SAT o del IRS?

**Por qué importa.** El número exacto lo dicta Legal a través de usted, no ingeniería, y condiciona el dimensionado: en el peor caso un ticket ocupa ~145 MB y el disco de capa gratuita es de 1 GB compartido con la base, las fotos y los paquetes. Una purga mal fijada borra evidencia que después no se recupera. Y hay un conflicto real que necesita respuesta de Legal: cuando un proveedor pida la supresión de sus datos, el gasto fiscal que lo cita debe conservarse — el diseño propone borrar el contacto y conservar el nombre.

**Opciones:**

1. Comprobantes 7 años tras el cierre del ejercicio (cubre los 5 del SAT y los 3-7 del IRS); paquetes ZIP purgados a los 90 días, siempre regenerables
2. Comprobantes 5 años (mínimo SAT); paquetes 30 días
3. Sin purga automática hasta que Legal fije el número

**Recomendación.** La primera, pero necesito el número por escrito de Legal antes de construir la purga. Los topes actuales por ticket se mantienen hasta tener un caso real que los desborde: subirlos es cambiar una constante, pero cuesta disco que no tenemos.

---

### D-027 · Módulo fiscal: apruebe el texto del descargo legal, confirme que el tipo de cambio lo teclea usted declarando su fuente, y dígame si tiene hoy alguna propiedad en Estados Unidos o el soporte a IRS es previsión.

**Por qué importa.** El descargo («Aura registra y organiza sus datos de gastos; no da asesoría fiscal, no calcula impuestos, no determina qué es deducible, no valida ni timbra CFDI y no presenta ninguna declaración; el etiquetado SAT / IRS Schedule E es orientativo») va en la pantalla del año fiscal y en la portada de cada paquete. Sin su firma en esa frase, la pantalla no se publica. Sobre el tipo de cambio: si la plataforma lo consultara sola, produciría una cifra cuyo origen no podríamos justificar ante un auditor; tecleándolo usted, cada línea del CSV imprime la tasa y su fuente. Y si no hay tasa cargada, la celda en USD va VACÍA y el paquete lo declara: un paquete visiblemente incompleto es mejor que uno silenciosamente falso.

**Opciones:**

1. Aprobar el texto propuesto como borrador, con revisión de su abogado después; tasa manual con fuente obligatoria; el mapeo IRS se construye igual pero solo se prueba con México
2. Texto redactado por su abogado desde cero antes de construir
3. Hay propiedad en EE. UU. hoy: el mapeo IRS entra en el camino crítico y se prueba con datos reales

**Recomendación.** La primera, salvo que me diga que ya tiene propiedad en EE. UU. El esquema y el catálogo son idénticos en ambos casos; lo que cambia es si el tipo de cambio entra en el camino crítico ahora y cuánta pantalla ocupa la columna del IRS.

---

### D-028 · Agente IA y correo entrante: el tope de gasto es hoy MENSUAL y GLOBAL en dólares. ¿Pasa a ser por cuenta ligado al plan? ¿Se contrata el servicio de correo entrante que necesita el primer paso del 7.4? ¿Podrá la plataforma escribirle alguna vez al proveedor?

**Por qué importa.** Tres decisiones que van juntas y son de negocio, no técnicas. (1) Con el tope global, en cuanto venda a otra administradora, el primer cliente que use cotización automática deja sin presupuesto a todos los demás; además el control falla hacia el gasto ante cualquier error. (2) El correo entrante exige contratar un proveedor con webhook, lo que rompe la regla de free-tier — y sin verificación SPF/DKIM/DMARC y sin lista blanca remitente→arrendamiento, cualquiera que aprenda la dirección crea tickets en la cola de cualquier propietario: es inyección directa a su bandeja y a un agente que gasta dinero. (3) Escribirle al proveedor significa aceptar que fotos del INTERIOR de la vivienda de un inquilino viajen a un tercero.

**Opciones:**

1. Tope por cuenta ligado al plan; NO contratar correo entrante por ahora (el 7.4 se queda con entrada manual); la plataforma NUNCA escribe al proveedor y la asignación es una anotación interna
2. Autorizar el gasto del servicio de correo entrante
3. Habilitar el envío al proveedor cuando Legal firme, con consentimiento explícito por ticket y selección MANUAL de fotos, ninguna por defecto

**Recomendación.** La primera en las tres. El tope por cuenta es la única variante que no permite que un cliente deje sin servicio a los demás. Las otras dos conviene decidirlas juntas y no por separado, y ninguna es urgente mientras el agente siga desconectado.

---

### D-029 · Personal de Aura con rol admin puede leer hoy los datos de los inquilinos de CUALQUIER cuenta, y la bitácora que registra todo eso no la muestra ninguna pantalla. ¿Se aprueba la pantalla de bitácora como requisito PREVIO al segundo cliente real?

**Por qué importa.** Verificado: el aislamiento se cortocircuita para el rol admin en las cuatro funciones de scoping. Hoy eso era usted mirando sus propias casas; con clientes reales es personal del proveedor leyendo nombre, teléfono y fotos del interior de la vivienda de los inquilinos de sus clientes. Y verifiqué que `security.audit()` escribe en la tabla de bitácora pero NINGUNA de las 27 plantillas la lee: el aviso de deriva de cuentas, el rastro de las reasignaciones de propiedad, quién descargó qué comprobante y quién exportó un paquete fiscal con fotos del interior de una vivienda — todo queda escrito y nadie puede consultarlo salvo por SQL. La trazabilidad de este lote es teórica.

**Opciones:**

1. Aprobarla como condición previa al segundo cliente real: pantalla de bitácora + registro específico de toda lectura de admin sobre pantallas de otra cuenta con datos de inquilinos
2. Dejarlo como está y revisarlo más adelante

**Recomendación.** La primera, y no como mejora opcional. Es una pantalla pequeña y el mitigante es barato; lo que no es barato es explicar, después de un incidente, que el rastro existía y nadie podía verlo.

---

## Pueden esperar

### D-030 · Paquete de valores por defecto que el diseño ya fijó y que solo necesitan un «de acuerdo» suyo (o una corrección).

**Por qué importa.** Doce decisiones pequeñas que no bloquean nada pero que se vuelven caras si se cambian después de construir. Van juntas para no gastarle doce vueltas.

**Opciones:**

1. Ocupación % = contratos activos ÷ total (no el estatus del sitio público) · Panel v1 sin NINGUNA cifra de dinero hasta que la renta se capture de verdad · Tramos de m²: hasta 80 / 80-150 / más de 150 (con su cartera real el tramo intermedio queda vacío) · «Selección» de casas efímera en la dirección del navegador, sin carteras con nombre · Renombrar «Mis propiedades» → «Panel» · Cuando el sitio público y el contrato no coincidan, el panel solo AVISA y el administrador corrige donde vive el dato · El inquilino ve las fotos del trabajo terminado pero nunca la factura, el importe ni el nombre del proveedor · El inquilino con clave temporal queda bloqueado hasta poner una propia (afecta a los ya dados de alta) · Botón «ver contraseña» en las cinco pantallas, no solo en la de acceso · El enlace de recuperación NUNCA se imprime en pantalla; se ve en un buzón de salida que exige sesión de administrador y modo pruebas · Se cargan 2024 y 2025 y nacen ABIERTOS, y usted los cierra al terminar la captura · El propietario cierra y reabre un año fiscal con motivo escrito; el admin de Aura no reabre nunca por su cuenta · El XML del CFDI se guarda como bytes opacos y NADIE lo parsea (usted teclea el UUID) · Vencer la prueba el día 91 NO impide que un inquilino abra un ticket de mantenimiento
2. Corregir alguno — dígame cuál y le digo qué hay que construir antes

**Recomendación.** Apruebe el bloque tal cual. Dos que conviene que lea dos veces: el panel sin cifras de dinero (el precio de lista es lo que se anuncia, no lo pactado, y si aparece acabará arrastrado al módulo fiscal y lo verá un contador) y el día 91 (una fuga de agua no sabe nada de suscripciones; cortar el canal por el que se reporta una avería convierte un impago en un problema de habitabilidad).

---
