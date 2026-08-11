#!/bin/sh
# Arranque del contenedor.
#
# Existe por un detalle de los volúmenes: Fly (y Docker en general) monta el
# volumen VACÍO y propiedad de root, tapando el directorio que el Dockerfile
# creó en la imagen. Como la aplicación corre con una cuenta sin privilegios,
# sin este ajuste no podría escribir la base de datos ni las fotos, y el
# arranque fallaría con "permission denied" — un error que en un despliegue
# remoto cuesta bastante diagnosticar.
#
# La secuencia es: entrar como root SOLO para ajustar permisos, y ejecutar la
# aplicación como `aura`. El proceso servidor nunca corre como root.
set -e

mkdir -p /data/uploads
chown -R aura:aura /data

# `exec` sustituye este shell por uvicorn, para que reciba las señales de
# parada directamente y el contenedor se detenga de forma limpia.
exec su aura -s /bin/sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1'
