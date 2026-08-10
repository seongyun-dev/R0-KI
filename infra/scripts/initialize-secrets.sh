#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "initialize-secrets.sh must run as root" >&2
  exit 1
fi

secret_dir=/srv/aiot/secrets
runtime_env="${secret_dir}/runtime.env"
backend_env="${secret_dir}/backend.env"
robot_env="${secret_dir}/robot-mqtt.env"
passwd_file=/srv/aiot/config/mosquitto/passwd
passwd_tmp=/srv/aiot/config/mosquitto/passwd.new

install -d -m 2770 -o root -g aiot "${secret_dir}"
umask 0077

if [ ! -f "${runtime_env}" ]; then
  mysql_root_password=$(openssl rand -hex 32)
  mysql_password=$(openssl rand -hex 32)
  mqtt_robot_password=$(openssl rand -hex 24)
  mqtt_backend_password=$(openssl rand -hex 24)

  cat >"${runtime_env}" <<EOF
MYSQL_DATABASE=aiot
MYSQL_USER=aiot_app
MYSQL_ROOT_PASSWORD=${mysql_root_password}
MYSQL_PASSWORD=${mysql_password}
MQTT_ROBOT_USERNAME=robot-01
MQTT_ROBOT_PASSWORD=${mqtt_robot_password}
MQTT_BACKEND_USERNAME=spring-backend
  MQTT_BACKEND_PASSWORD=${mqtt_backend_password}
EOF
fi

if ! grep -q '^APP_JWT_SECRET=' "${runtime_env}"; then
  app_jwt_secret=$(openssl rand -hex 48)
  printf 'APP_JWT_SECRET=%s\n' "${app_jwt_secret}" >>"${runtime_env}"
fi

# shellcheck disable=SC1090
source "${runtime_env}"

cat >"${backend_env}" <<EOF
SPRING_DATASOURCE_URL=jdbc:mysql://aiot-mysql:3306/${MYSQL_DATABASE}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Seoul
SPRING_DATASOURCE_USERNAME=${MYSQL_USER}
SPRING_DATASOURCE_PASSWORD=${MYSQL_PASSWORD}
MQTT_BROKER_URI=tcp://aiot-mosquitto:1883
MQTT_USERNAME=${MQTT_BACKEND_USERNAME}
MQTT_PASSWORD=${MQTT_BACKEND_PASSWORD}
APP_JWT_SECRET=${APP_JWT_SECRET}
APP_JWT_ACCESS_TOKEN_EXPIRATION=28800000
APP_CORS_ALLOWED_ORIGINS=https://i15e103.p.ssafy.io
UPLOAD_DIR=/app/data/uploads
MAP_DIR=/app/data/maps
EOF

cat >"${robot_env}" <<EOF
MQTT_HOST=i15e103.p.ssafy.io
MQTT_PORT=8883
MQTT_TLS=true
MQTT_USERNAME=${MQTT_ROBOT_USERNAME}
MQTT_PASSWORD=${MQTT_ROBOT_PASSWORD}
MQTT_CA_SYSTEM=true
EOF

docker pull eclipse-mosquitto:2 >/dev/null
rm -f "${passwd_tmp}"
docker run --rm --user 0:0 \
  --env-file "${runtime_env}" \
  -v /srv/aiot/config/mosquitto:/work \
  --entrypoint sh eclipse-mosquitto:2 -ec '
    mosquitto_passwd -c -b /tmp/aiot-passwd "$MQTT_ROBOT_USERNAME" "$MQTT_ROBOT_PASSWORD"
    mosquitto_passwd -b /tmp/aiot-passwd "$MQTT_BACKEND_USERNAME" "$MQTT_BACKEND_PASSWORD"
    cp /tmp/aiot-passwd /work/passwd.new
    chown 1883:0 /work/passwd.new
    chmod 0600 /work/passwd.new
  '

mv -f "${passwd_tmp}" "${passwd_file}"

chown root:aiot "${runtime_env}" "${backend_env}" "${robot_env}"
chmod 0640 "${runtime_env}" "${backend_env}" "${robot_env}"
chown 1883:1883 "${passwd_file}"
chmod 0600 "${passwd_file}"

echo "Secrets initialized without printing secret values"
