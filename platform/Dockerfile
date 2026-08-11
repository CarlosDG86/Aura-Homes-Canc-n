# Imagen de la plataforma (API + páginas de gestión).
#
# Se construye desde `platform/`, no desde la raíz del repositorio: el sitio
# público es una aplicación distinta y no tiene por qué viajar dentro de esta
# imagen (INFRA_STACK.md §4).
FROM python:3.12-slim

# - PYTHONDONTWRITEBYTECODE: sin .pyc en la imagen, que no aportan nada.
# - PYTHONUNBUFFERED: los registros salen al instante y no se pierden si el
#   contenedor muere de golpe.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Las dependencias se copian antes que el código para que Docker reutilice la
# capa cuando solo cambia el código: reconstruir pasa de minutos a segundos.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# La aplicación NO corre como root. Si alguien lograra ejecutar algo dentro del
# contenedor, lo hace con una cuenta sin privilegios.
RUN useradd --create-home --uid 10001 aura \
    && mkdir -p /data/uploads \
    && chown -R aura:aura /data /srv

COPY docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# El contenedor arranca como root a propósito, pero SOLO para ajustar los
# permisos del volumen: el entrypoint baja a la cuenta `aura` antes de lanzar
# el servidor. Fly monta el volumen vacío y propiedad de root, tapando el
# directorio creado arriba; sin ese ajuste la aplicación no podría escribir.

# /data es el volumen persistente: ahí viven la base SQLite y las fotos de los
# tickets. Sin volumen montado, ambos se pierden en cada despliegue.
VOLUME ["/data"]
ENV DATABASE_URL="sqlite:////data/platform.db" \
    UPLOAD_DIR="/data/uploads" \
    APP_ENV="production"

EXPOSE 8080

# Un solo worker a propósito: SQLite no admite varios procesos escribiendo a la
# vez sobre el mismo archivo. Si algún día hace falta escalar, el paso es
# Postgres, no más workers (INFRA_STACK.md §2).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
