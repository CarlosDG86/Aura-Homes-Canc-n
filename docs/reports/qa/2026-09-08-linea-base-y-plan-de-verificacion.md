# QA — Reporte de estado

**Fecha:** 2026-09-08
**Periodo:** línea base de pruebas y plan de verificación de la Fase 2.1
**Archivado en:** Aura/Reports/QA/

---

## 1. Resumen

**En marcha.** La suite completa está en verde y se midió hoy: **261 comprobaciones, 0 fallos,
10 suites**. Se verificó también que ninguna prueba toca la base real.

QA no ha dado visto bueno a nada nuevo porque no hay nada nuevo que revisar: la Fase 2.1 está en
diseño y no se ha escrito código. Lo que sí hay es **tres defectos confirmados en el código
actual**, dos de ellos reproducidos con prueba propia.

---

## 2. Completado

### 2.1 Línea base medida

```
  OK    test_e1.py                27 pasaron, 0 fallaron
  OK    test_e2.py                25 pasaron, 0 fallaron
  OK    test_inbox.py             21 pasaron, 0 fallaron
  OK    test_migrate.py          (sin resumen, código 0)
  OK    test_owner_portal.py      38 pasaron, 0 fallaron
  OK    test_scoping.py           27 pasaron, 0 fallaron
  OK    test_sessions.py          24 pasaron, 0 fallaron
  OK    test_sso.py               25 pasaron, 0 fallaron
  OK    test_tenant.py            33 pasaron, 0 fallaron
  OK    test_ui.py                41 pasaron, 0 fallaron

TOTAL: 261 pasaron, 0 fallaron, en 10 suites
```

### 2.2 Verificado que las pruebas no tocan la base real

`sha256` de `platform/data/platform.db` idéntico antes y después de la ejecución completa. Cada
suite crea su propia base desechable en un directorio temporal.

---

## 3. En curso

Nada. A la espera de que se construya E8.

---

## 4. Bloqueadores

### 4.1 Tres defectos del código actual

**H-1 — la API JSON evade todos los controles de acceso.** Reproducido:

```
20 intentos fallidos por CADA vía, mismo usuario
  HTML  /login          -> 401 … 429  (frena)
  API   /api/auth/login -> 401 ×20    (nunca frena)
  Filas en login_attempts: 10  (la API no registra ninguna)
  Clave correcta por la API tras el bloqueo -> 200 (ENTRÓ)
```

Un administrador **desactivado, bloqueado y con 99 fallos** entró por la API y leyó
`/api/admin/users`. El camino HTML lo rechazó con 302.

**H-2 — el modo simulación no impide enviar un correo real con la contraseña en claro.**
Reproducido interceptando el envío. Lo único que lo detiene hoy es que `SMTP_PASSWORD` está
vacío; `SMTP_HOST` y `SMTP_USER` sí tienen valor.

**H-3 — el sitio público en vivo enlaza a un host caído** desde el menú «Ingresar», en 22
páginas. Medido: el sitio devuelve 200, `aura-homes-plataforma.fly.dev` no responde.

### 4.2 Tres problemas en la propia suite

| Problema | Efecto |
|---|---|
| `test_migrate.py` no imprime la línea `RESULTADO:` | Sus 7 comprobaciones **no suman** al total; `run_all.py` lo aprueba solo por el código de salida |
| Rutas absolutas de Windows en `test_migrate.py:3-4` | Esa suite no puede correr en el CI de Linux |
| El paso «Suite completa» se retiró del flujo de despliegue | Nada ejecuta las pruebas solo |

---

## 5. Decisiones que esperan al CEO

**5.1 ¿Se arregla `test_migrate.py` como parte del lote?**
- A: Sí — añadir la línea `RESULTADO:` y sustituir las rutas absolutas por una base de prueba
  anonimizada versionada en el repositorio.
- B: Dejarlo; sus 7 comprobaciones seguirán sin contar.
- **Recomendación: A.** Es la suite que verifica las migraciones, y la Fase 2.1 es el lote de
  migraciones más grande hasta la fecha. Que no cuente es justo lo contrario de lo que hace falta.

**5.2 ¿Vuelve el paso de pruebas al flujo automático?**
- A: Sí, ejecutando la suite en cada cambio.
- B: Seguir a mano con `python tests/run_all.py`.
- **Recomendación: A**, una vez resuelto 5.1 — hoy dos suites reventarían en Linux.

---

## 6. Plan de verificación por etapa

Qué comprueba QA antes de dar por hecha cada etapa. **162 comprobaciones nuevas** en total.

| Etapa | Verificación de aceptación |
|---|---|
| **E8** | Reproducir H-1 **antes** y comprobar que deja de reproducirse **después**: 20 POST fallidos devuelven 404 (no 401); un usuario con `is_active=False` y bloqueado ya no lee `/api/admin/users`; tras revocar la sesión, el acceso muere |
| **E9** | `--simular` pasa dos veces seguidas con diferencia vacía la segunda; sobre copia de la base real: 0 `account_id` nulos, y **los 3 usuarios y las 3 propiedades idénticos** a antes |
| **E10** | Un correo existente y uno inexistente devuelven respuesta **carácter a carácter idéntica**; el token crudo no aparece en ninguna respuesta ni cabecera; en base se guarda su hash |
| **E11** | Existe **una sola** ruta `GET /owner`; el número de consultas SQL no crece con el número de propiedades; un identificador ajeno devuelve lista vacía, nunca datos ajenos |
| **E12** | **La regresión más importante del lote:** `POST /owner/tickets/{id}/actualizar` sigue aceptando el formato actual y sigue devolviendo 400 al resolver sin nota. Un `.txt` renombrado a `.pdf` y un ejecutable dan 400 sin dejar archivo |
| **E13** | Un identificador de propiedad ajeno inyectado en el formulario da 404 sin crear fila; un gasto sin tipo de cambio nunca produce un importe inventado |
| **E14** | Cada suma de verificación declarada en el paquete coincide con su archivo; **sin marcar la casilla, el paquete no contiene ninguna foto** |

---

## 7. Costo

Sin impacto.
