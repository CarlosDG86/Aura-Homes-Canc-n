# QA — Reporte de estado

**Fecha:** 2026-10-04
**Periodo:** verificación de las etapas E8 a E14
**Archivado en:** Aura/Reports/QA/

---

## 1. Resumen

**En marcha.** La suite completa está en verde: **722 comprobaciones, 0 fallos, 17 suites**.
Eran 261 en 10 suites en la línea base del 2026-09-08.

Los tres defectos que QA había confirmado en septiembre: **dos cerrados con prueba propia**
(el agujero de acceso por la API y la fuga de contraseña en claro por correo). **El tercero
sigue abierto** y no lo puede cerrar QA: los enlaces del sitio público requieren republicar.

QA **no ha dado visto bueno a ningún despliegue**, porque no se ha propuesto ninguno.

---

## 2. Medición de hoy

```
  OK    test_acceso.py            60 pasaron, 0 fallaron
  OK    test_cuentas.py           47 pasaron, 0 fallaron
  OK    test_e1.py                27 pasaron, 0 fallaron
  OK    test_e14.py              139 pasaron, 0 fallaron
  OK    test_e2.py                25 pasaron, 0 fallaron
  OK    test_e8.py                22 pasaron, 0 fallaron
  OK    test_fiscal.py            64 pasaron, 0 fallaron
  OK    test_inbox.py             21 pasaron, 0 fallaron
  OK    test_migrate.py          (sin resumen, código 0)
  OK    test_owner_dashboard.py   57 pasaron, 0 fallaron
  OK    test_owner_portal.py      50 pasaron, 0 fallaron
  OK    test_proveedores.py       60 pasaron, 0 fallaron
  OK    test_scoping.py           27 pasaron, 0 fallaron
  OK    test_sessions.py          24 pasaron, 0 fallaron
  OK    test_sso.py               25 pasaron, 0 fallaron
  OK    test_tenant.py            33 pasaron, 0 fallaron
  OK    test_ui.py                41 pasaron, 0 fallaron

TOTAL: 722 pasaron, 0 fallaron, en 17 suites
```

Comando: `cd platform && python tests/run_all.py`

**Ninguna prueba toca la base real.** Cada suite crea su propia base en un directorio temporal
y la exportación fiscal escribe en un directorio temporal propio, no en `data/`. Verificado:
el hash de `platform.db` es idéntico antes y después de la sesión completa.

---

## 3. Las comprobaciones que más valen de E14

Por si hay que priorizar una revisión manual, estas son las que protegen algo que no se puede
deshacer:

1. **Ningún dato de contacto del inquilino sale del paquete fiscal.** La prueba busca su
   nombre, su correo y su teléfono en todos los archivos de texto del ZIP.
2. **Las fotos del interior no salen si nadie marcó la casilla**, y la pantalla intermedia no
   se puede saltar armando la petición a mano.
3. **Un límite de plan nunca bloquea leer, resolver un ticket, exportar ni que un inquilino
   reporte una avería.** Esa última tiene prueba propia y es la que más fácil se rompe en un
   refactor.
4. **Los hashes del paquete coinciden** con el contenido real de cada archivo, y el hash del
   ZIP coincide con el registrado en la base.
5. **Aprobar una cotización no cambia el estado del ticket ni le asigna proveedor** (D-017).

---

## 4. Lo que QA no ha podido verificar

| Qué | Por qué |
|---|---|
| Lighthouse móvil 90+ | Nunca se ha medido. Se quitaron frenos evidentes, pero eso no es haberlo comprobado |
| El paquete fiscal abierto por un contador real | Nadie fuera del equipo lo ha abierto en Excel ni en su software contable |
| Comportamiento con volumen | La base de pruebas tiene 3 propiedades. El tope de filas de CSV es 5 000 y el del paquete 200 MB, ninguno se ha ejercitado de verdad |
| Correo saliente | No hay buzón de producción (D-023) |
| El segundo factor del administrador en un teléfono real | Se prueba con código generado, no con una app |

---

## 5. Defectos abiertos

- **Enlaces «Ingresar» del sitio público** (22 páginas) apuntan a un host que no responde.
  Requiere republicar el sitio: aprobación del CEO.
- **`test_migrate.py`** conserva rutas absolutas de Windows y no imprime línea de resultado,
  así que sus 7 comprobaciones no suman al total y reventarían en Linux.
- **El paso de suite completa se retiró del flujo de despliegue.** Hoy las pruebas solo corren
  cuando alguien las lanza a mano.

---

## 6. Próximos pasos

- Arreglar `test_migrate.py` y reponerlo al total.
- Volver a poner la suite en el flujo automático.
- Medir Lighthouse móvil y dejar la cifra por escrito.
- Cargar contratos de arrendamiento para poder verificar el indicador de ocupación con datos.

---

## 7. Costo

Cero. Todo corre en local.
