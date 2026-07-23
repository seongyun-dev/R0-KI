#!/usr/bin/env bash
set -euo pipefail

health_check_script="${HEALTH_CHECK_SCRIPT:-/srv/aiot/deploy/health-check.sh}"
backup_root="${BACKUP_ROOT:-/srv/aiot/backups/runtime}"
certificate_path="${CERTIFICATE_PATH:-/srv/aiot/certs/mqtt/fullchain.pem}"
disk_path="${DISK_PATH:-/srv/aiot}"
disk_warning="${DISK_WARNING_PERCENT:-80}"
disk_critical="${DISK_CRITICAL_PERCENT:-90}"
backup_max_age="${BACKUP_MAX_AGE_SECONDS:-93600}"
certificate_warning_days="${CERTIFICATE_WARNING_DAYS:-21}"
certificate_critical_days="${CERTIFICATE_CRITICAL_DAYS:-14}"

warnings=0
criticals=0

report() {
  local level="$1"
  local check="$2"
  shift 2
  printf 'aiot-monitor level=%s check=%s message=%s\n' "${level}" "${check}" "$*"
  case "${level}" in
    warning) warnings=$((warnings + 1)) ;;
    critical) criticals=$((criticals + 1)) ;;
  esac
}

if bash "${health_check_script}" application; then
  report ok runtime healthy
else
  report critical runtime health-check-failed
fi

disk_percent="$(df -P "${disk_path}" | awk 'NR == 2 {gsub(/%/, "", $5); print $5}')"
if [[ ! "${disk_percent}" =~ ^[0-9]+$ ]]; then
  report critical disk unreadable
elif [ "${disk_percent}" -ge "${disk_critical}" ]; then
  report critical disk "usage-${disk_percent}-percent"
elif [ "${disk_percent}" -ge "${disk_warning}" ]; then
  report warning disk "usage-${disk_percent}-percent"
else
  report ok disk "usage-${disk_percent}-percent"
fi

latest_backup="$(
  find "${backup_root}" -mindepth 1 -maxdepth 1 -type d \
    -name '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-*' \
    -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -n 1 | cut -d' ' -f2- || true
)"
if [ -z "${latest_backup}" ]; then
  report critical backup missing
else
  backup_epoch="$(stat -c '%Y' "${latest_backup}")"
  backup_age=$(( $(date +%s) - backup_epoch ))
  if [ ! -s "${latest_backup}/SHA256SUMS" ]; then
    report critical backup missing-checksums
  elif [ ! -s "${latest_backup}/COMPLETED" ]; then
    report warning backup legacy-without-completion-marker
  fi
  if [ "${backup_age}" -gt "${backup_max_age}" ]; then
    report critical backup "stale-${backup_age}-seconds"
  else
    report ok backup "fresh-${backup_age}-seconds"
  fi
fi

if [ ! -r "${certificate_path}" ]; then
  report critical certificate missing
else
  certificate_end="$(openssl x509 -enddate -noout -in "${certificate_path}" | cut -d= -f2-)"
  certificate_epoch="$(date -d "${certificate_end}" +%s)"
  certificate_days=$(( (certificate_epoch - $(date +%s)) / 86400 ))
  if [ "${certificate_days}" -lt "${certificate_critical_days}" ]; then
    report critical certificate "expires-in-${certificate_days}-days"
  elif [ "${certificate_days}" -lt "${certificate_warning_days}" ]; then
    report warning certificate "expires-in-${certificate_days}-days"
  else
    report ok certificate "expires-in-${certificate_days}-days"
  fi
fi

report ok summary "warnings-${warnings}-criticals-${criticals}"
if [ "${criticals}" -gt 0 ]; then
  exit 2
fi
if [ "${warnings}" -gt 0 ]; then
  exit 1
fi
