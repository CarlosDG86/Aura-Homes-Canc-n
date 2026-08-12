"""Crea una copia consistente de la base y las fotos, dentro del contenedor.

Se ejecuta desde GitHub Actions con:

    flyctl ssh console -C "python -m app.backup"

y deja un `.tar.gz` en /tmp cuya ruta imprime en la última línea, para que el
flujo la recoja con `sftp get`.

Dos decisiones que importan:

1. **`sqlite3.Connection.backup()`, no `cp`.** Copiar el archivo mientras la
   aplicación escribe puede capturar una transacción a medias y producir una
   base corrupta — que es peor que no tener respaldo, porque parece que sí lo
   tienes. La API de respaldo de SQLite toma una instantánea coherente con la
   aplicación en marcha.

2. **Se escribe en /tmp, no en el volumen.** El volumen es de 1 GB y ahí viven
   la base y las fotos en producción; llenarlo con respaldos tumbaría la
   aplicación, justo lo que el respaldo pretende evitar. /tmp vive en el disco
   efímero del contenedor y desaparece al reiniciar, que es lo que queremos:
   la copia solo tiene que sobrevivir hasta que Actions la descargue.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tarfile
import tempfile

DATA_DIR = os.environ.get("BACKUP_DATA_DIR", "/data")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))

#: Ambas bases: `platform.db` es la de producción y `platform-mock.db` la de
#: simulación. Hoy `DATABASE_URL` apunta a la primera aunque `DATA_MODE=mock`,
#: pero se respaldan las dos: cuál está en uso es una variable de entorno que
#: puede cambiar, y un respaldo que depende de eso se rompe en silencio.
DB_NAMES = ("platform.db", "platform-mock.db")


def _snapshot(src: str, dst: str) -> dict:
    """Instantánea coherente de una base SQLite en caliente."""
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
            # Comprobar la copia, no el original: lo que se guarda es esto.
            ok = target.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RuntimeError(f"{src}: la copia no pasa integrity_check ({ok})")
            tables = {
                name: target.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for (name,) in target.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            }
        finally:
            target.close()
    finally:
        source.close()
    return {"bytes": os.path.getsize(dst), "tables": tables}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    work = tempfile.mkdtemp(prefix="aura-backup-")
    manifest: dict = {"databases": {}, "photos": {"files": 0, "bytes": 0}}

    for name in DB_NAMES:
        src = os.path.join(DATA_DIR, name)
        if not os.path.exists(src):
            continue
        manifest["databases"][name] = _snapshot(src, os.path.join(work, name))

    if not manifest["databases"]:
        # Sin base no hay nada que restaurar. Fallar es correcto: un respaldo
        # vacío que se sube como si todo hubiera ido bien es el peor resultado.
        print(f"ERROR: no se encontró ninguna base en {DATA_DIR}", file=sys.stderr)
        return 1

    out = os.path.join(tempfile.gettempdir(), "aura-backup.tar.gz")
    with tarfile.open(out, "w:gz") as tar:
        for name in manifest["databases"]:
            tar.add(os.path.join(work, name), arcname=f"db/{name}")

        if os.path.isdir(UPLOAD_DIR):
            for root, _dirs, files in os.walk(UPLOAD_DIR):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, UPLOAD_DIR)
                    tar.add(full, arcname=f"uploads/{rel}".replace("\\", "/"))
                    manifest["photos"]["files"] += 1
                    manifest["photos"]["bytes"] += os.path.getsize(full)

        meta = os.path.join(work, "manifest.json")
        with open(meta, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        tar.add(meta, arcname="manifest.json")

    manifest["archive"] = {"path": out, "bytes": os.path.getsize(out), "sha256": _sha256(out)}
    print(json.dumps(manifest, ensure_ascii=False))
    print(out)  # última línea: la ruta, que es lo que lee el flujo de Actions
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
