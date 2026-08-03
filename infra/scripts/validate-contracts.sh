#!/usr/bin/env bash
set -euo pipefail

errors=0

fail() {
  echo "contract error: $*" >&2
  errors=$((errors + 1))
}

if [ -f frontend/package.json ]; then
  [ -f frontend/package-lock.json ] || fail "frontend/package-lock.json is required"
  [ -f frontend/Dockerfile ] || fail "frontend/Dockerfile is required"
  [ -f frontend/.dockerignore ] || fail "frontend/.dockerignore is required"
  [ -f frontend/nginx.conf ] || fail "frontend/nginx.conf is required"
  node -e '
    const pkg = require("./frontend/package.json");
    if (!pkg.scripts || !pkg.scripts.build) {
      throw new Error("frontend package.json must define scripts.build");
    }
  ' || fail "frontend build script is invalid"
fi

if [ -f backend/build.gradle ] || [ -f backend/build.gradle.kts ]; then
  [ -f backend/gradlew ] || fail "backend/gradlew is required"
  [ -f backend/Dockerfile ] || fail "backend/Dockerfile is required"
  [ -f backend/.dockerignore ] || fail "backend/.dockerignore is required"
fi

if find ai -type f -name '*.py' -print -quit 2>/dev/null | grep -q .; then
  if [ ! -f ai/requirements.txt ] && [ ! -f ai/pyproject.toml ]; then
    fail "ai/requirements.txt or ai/pyproject.toml is required when AI code exists"
  fi
fi

if find robot -type f -name '*.py' -print -quit 2>/dev/null | grep -q .; then
  if [ ! -f robot/requirements.txt ] && [ ! -f robot/pyproject.toml ] && \
     [ ! -f robot/package.xml ]; then
    fail "robot dependency or ROS package manifest is required when robot code exists"
  fi
fi

for required_file in \
  infra/smoke/compose.smoke.yaml \
  infra/smoke/frontend/Dockerfile \
  infra/smoke/frontend/package.json \
  infra/smoke/frontend/package-lock.json \
  infra/smoke/backend/Dockerfile \
  infra/smoke/backend/Dockerfile.deploy \
  infra/smoke/backend/deploy-nginx.conf \
  infra/smoke/backend/build.gradle; do
  [ -f "${required_file}" ] || fail "${required_file} is required"
done

nginx_template=infra/nginx/aiot.conf.template
for required_route in \
  'location = /api/internal/stream-sessions/validate {' \
  'location = /live/robots/16/stream.mjpg {' \
  'location = /_live_robot_stream_auth {' \
  'location = /swagger-ui.html {' \
  'location ^~ /swagger-ui/ {' \
  'location = /v3/api-docs {' \
  'location ^~ /v3/api-docs/ {'; do
  grep -Fq "${required_route}" "${nginx_template}" || \
    fail "${nginx_template} must proxy ${required_route}"
done

if [ "${errors}" -ne 0 ]; then
  echo "${errors} component contract error(s) found" >&2
  exit 1
fi

echo "Component contracts validated"
