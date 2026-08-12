"""Ejecuta las diez suites y devuelve un solo código de salida.

Cada suite es un guion independiente que crea su propia base desechable y sale
con 1 si algo falla. Este ejecutor las corre en subprocesos separados a
propósito: comparten nombres de módulo y variables de entorno
(`DATABASE_URL`), así que importarlas en el mismo proceso haría que una suite
contaminara a la siguiente y los resultados dejarían de significar nada.

Uso:
    cd platform && python tests/run_all.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent
RESUMEN = re.compile(r"RESULTADO:\s*(\d+)\s*pasaron,\s*(\d+)\s*fallaron")


def main() -> int:
    suites = sorted(RAIZ.glob("test_*.py"))
    if not suites:
        print("ERROR: no se encontró ninguna suite", file=sys.stderr)
        return 1

    total_ok = total_fail = 0
    rotas: list[str] = []

    for suite in suites:
        r = subprocess.run(
            [sys.executable, str(suite)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=RAIZ.parent,
        )
        salida = (r.stdout or "") + (r.stderr or "")
        m = RESUMEN.search(salida)
        if m:
            ok, fail = int(m.group(1)), int(m.group(2))
            total_ok += ok
            total_fail += fail
            estado = "OK  " if fail == 0 and r.returncode == 0 else "FALLA"
            print(f"  {estado}  {suite.name:24} {ok:3} pasaron, {fail} fallaron")
        else:
            # Sin línea de resumen la suite reventó antes de terminar: eso es un
            # fallo, no un cero. Contarlo como "0 fallos" ocultaría el problema.
            estado = "OK  " if r.returncode == 0 else "ROTA"
            print(f"  {estado}  {suite.name:24} (sin resumen, código {r.returncode})")

        if r.returncode != 0 or (m and int(m.group(2))):
            rotas.append(suite.name)
            for linea in salida.splitlines():
                if "FAIL" in linea or "Error" in linea or "Traceback" in linea:
                    print(f"          {linea.strip()[:160]}")

    print(f"\n{'=' * 58}")
    print(f"TOTAL: {total_ok} pasaron, {total_fail} fallaron, en {len(suites)} suites")
    if rotas:
        print(f"Suites con problemas: {', '.join(rotas)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
