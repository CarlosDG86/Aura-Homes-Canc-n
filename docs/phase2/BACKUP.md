# Respaldo y restauración de la plataforma

> Decisión 5.1 del reporte `docs/reports/dev/2026-08-11-phase2-en-produccion.md`.
> Antes de esto no había ningún respaldo: perder el volumen de Fly era perder
> la base de datos y todas las fotos de los tickets.

---

## 1. Qué se respalda, cuándo y dónde

| | |
|---|---|
| **Qué** | `platform.db`, `platform-mock.db` y todas las fotos de `/data/uploads` |
| **Cuándo** | Cada noche a las 02:00 hora de Cancún (08:00 UTC), y a mano cuando se quiera |
| **Dónde** | Artefacto cifrado del repositorio, en la pestaña **Actions** |
| **Cuánto se guarda** | 90 días (el máximo de GitHub) |
| **Cifrado** | AES-256 simétrico (GPG), con una frase de paso que solo tiene el CEO |
| **Costo** | $0 |

El respaldo **se verifica antes de guardarse**: se descarga, se abre la base, se
corre `PRAGMA integrity_check` y se contrastan los conteos de filas contra el
manifiesto. Si algo no cuadra, el trabajo falla y llega aviso — en vez de
acumular respaldos rotos durante meses y descubrirlo el día que hagan falta.

---

## 2. Puesta en marcha (una sola vez)

Faltan **dos secretos** en el repositorio. Sin ellos el respaldo falla al
primer paso con un mensaje que dice exactamente qué falta.

**2.1 Generar la frase de paso.** En tu equipo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

> ⚠️ **Guárdala fuera de este repositorio y fuera del chat** — en tu gestor de
> contraseñas o en Drive. Sin ella los respaldos son archivos ilegibles: no
> existe forma de recuperarlos. Es el único dato de todo el sistema que no se
> puede regenerar.

**2.2 Cargar los secretos** en GitHub →
`Settings` → `Secrets and variables` → `Actions` → `New repository secret`:

| Nombre | Valor |
|---|---|
| `BACKUP_PASSPHRASE` | La frase del paso 2.1 |
| `FLY_API_TOKEN` | `fly tokens create deploy -a aura-homes-plataforma` |

**2.3 Probarlo.** Pestaña `Actions` → `Respaldo` → `Run workflow`. Debe
terminar en verde y dejar un artefacto `respaldo-<número>`.

---

## 3. Restaurar

**Cuándo hace falta:** se perdió el volumen, la base se corrompió, o alguien
borró datos por error y hay que volver atrás.

**3.1 Descargar y descifrar.** Baja el artefacto de la pestaña `Actions`:

```bash
gpg --batch --decrypt --passphrase "TU_FRASE" --output aura-backup.tar.gz aura-backup.tar.gz.gpg
tar -xzf aura-backup.tar.gz
```

Quedan `db/platform.db`, `db/platform-mock.db`, `uploads/` y `manifest.json`.
Revisa el manifiesto: dice cuántas filas tenía cada tabla el día del respaldo.

**3.2 Comprobar antes de subir nada.** Restaurar una base rota encima de una
que aún funciona a medias empeora las cosas:

```bash
python -c "import sqlite3; print(sqlite3.connect('db/platform.db').execute('PRAGMA integrity_check').fetchone()[0])"
```

Debe imprimir `ok`.

**3.3 Subirla.** Detén la aplicación primero: si escribe mientras sustituyes el
archivo, la base vuelve a quedar inconsistente.

```bash
flyctl scale count 0 -a aura-homes-plataforma
```

```bash
flyctl ssh sftp shell -a aura-homes-plataforma
```

Dentro de esa sesión: `put db/platform.db /data/platform.db`, y lo mismo con
cada foto que haya que reponer. Después:

```bash
flyctl scale count 1 -a aura-homes-plataforma
```

**3.4 Verificar.** Entra a https://aura-homes-plataforma.fly.dev, revisa que
estén los propietarios y los reportes, y contrasta contra el manifiesto.

---

## 4. Límites conocidos

Conviene tenerlos presentes antes de que hagan falta, no después.

- **Se pierde hasta un día de trabajo.** El respaldo es nocturno; lo hecho
  entre el último respaldo y el fallo no se recupera. Para el volumen de uso
  actual es razonable; cuando entren pagos reales (fase 2c) habrá que revisarlo.
- **90 días de historia.** Es el máximo de los artefactos de GitHub. Si se
  necesita más, hay que sacarlos a otro almacenamiento.
- **La frase de paso no tiene recuperación.** Si se pierde, los respaldos se
  vuelven inservibles. Es el punto único de fallo de todo este mecanismo.
- **No cubre el sitio público.** No hace falta: el sitio vive entero en git y
  se regenera con `python build.py`.
- **Restaurar es manual.** A propósito: una restauración automática que se
  dispare sola puede sobrescribir datos buenos con datos viejos.

---

## 5. Cómo funciona por dentro

- `platform/app/backup.py` — corre **dentro** del contenedor. Usa
  `sqlite3.Connection.backup()` en vez de copiar el archivo: copiar mientras la
  aplicación escribe puede capturar una transacción a medias y producir una
  base corrupta que *parece* un respaldo válido. Escribe en `/tmp`, no en el
  volumen, para no llenar el disco de 1 GB que sostiene la producción.
- `.github/workflows/backup.yml` — despierta la máquina (duerme sola para
  entrar en la capa gratuita), lanza la instantánea, la descarga, la verifica,
  la cifra y la guarda. Borra la copia del contenedor al terminar, incluso si
  algún paso falló.
