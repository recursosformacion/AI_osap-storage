#!/usr/bin/env bash
# Job diario de sincronización de autoridad (Metabrainz/MusicBrainz).
# Se invoca desde un timer systemd (ver osap-storage-sync-authority.timer) o cron.
#
# Uso (como ocw):
#   /home/ocw/openmusicrepository.com/osap-storage/scripts/sync_authority_job.sh
#
# El job es idempotente: continúa desde el último paquete procesado (authority_sync_state).
# Registra en systemd journal (stdout) y en /var/log si se redirige.
set -euo pipefail

cd /home/ocw/openmusicrepository.com/osap-storage

exec ./.venv/bin/python -m infrastructure.cli sync-authority --max-packets 48
