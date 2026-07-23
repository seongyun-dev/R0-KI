#!/usr/bin/env bash
set -euo pipefail

event="${1:-}"
component="${2:-}"
started_epoch="${3:-$(date +%s)}"

case "${event}" in
  success|rolled_back|rollback_failed|failed|integration_failed|jetson_published|connection_test) ;;
  *)
    echo "usage: notify-mattermost.sh <success|rolled_back|rollback_failed|failed|integration_failed|jetson_published|connection_test> <frontend|backend|all|jetson> [started-epoch]" >&2
    exit 1
    ;;
esac

case "${component}" in
  frontend)
    component_label=Frontend
    component_path=frontend
    default_service_url=https://i15e103.p.ssafy.io
    ;;
  backend)
    component_label=Backend
    component_path=backend
    default_service_url=https://i15e103.p.ssafy.io
    ;;
  jetson)
    component_label=Jetson
    component_path=
    default_service_url=https://i15e103.p.ssafy.io/jetson/releases/stable/manifest.json
    ;;
  all)
    component_label=전체
    component_path=
    default_service_url=https://i15e103.p.ssafy.io
    ;;
  *)
    echo "Unknown notification component: ${component}" >&2
    exit 1
    ;;
esac

duration_text() {
  local total_seconds="$1"
  local hours minutes seconds
  if [ "${total_seconds}" -lt 0 ]; then total_seconds=0; fi
  hours=$((total_seconds / 3600))
  minutes=$(((total_seconds % 3600) / 60))
  seconds=$((total_seconds % 60))

  if [ "${hours}" -gt 0 ]; then
    printf '%d시간 %d분 %d초' "${hours}" "${minutes}" "${seconds}"
  elif [ "${minutes}" -gt 0 ]; then
    printf '%d분 %d초' "${minutes}" "${seconds}"
  else
    printf '%d초' "${seconds}"
  fi
}

change_summary() {
  local commit_sha="${CI_COMMIT_SHA:-}"
  local before_sha="${CI_COMMIT_BEFORE_SHA:-}"
  local commit_count file_count

  if [ -n "${MM_CHANGE_SUMMARY:-}" ]; then
    printf '%s' "${MM_CHANGE_SUMMARY}"
    return
  fi
  if [ "${component}" = jetson ]; then
    printf '%s' "${CI_COMMIT_TAG:-새 릴리스}"
    return
  fi
  if [ -z "${commit_sha}" ] || ! git cat-file -e "${commit_sha}^{commit}" 2>/dev/null; then
    printf '확인 불가'
    return
  fi

  if [ -n "${before_sha}" ] && [[ ! "${before_sha}" =~ ^0+$ ]] && \
     git cat-file -e "${before_sha}^{commit}" 2>/dev/null; then
    if [ -n "${component_path}" ]; then
      commit_count="$(git rev-list --count "${before_sha}..${commit_sha}" -- "${component_path}")"
      file_count="$(git diff --name-only "${before_sha}" "${commit_sha}" -- "${component_path}" | sed '/^$/d' | wc -l | tr -d ' ')"
    else
      commit_count="$(git rev-list --count "${before_sha}..${commit_sha}")"
      file_count="$(git diff --name-only "${before_sha}" "${commit_sha}" | sed '/^$/d' | wc -l | tr -d ' ')"
    fi
  else
    commit_count=1
    if [ -n "${component_path}" ]; then
      file_count="$(git show --pretty='' --name-only "${commit_sha}" -- "${component_path}" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')"
    else
      file_count="$(git show --pretty='' --name-only "${commit_sha}" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')"
    fi
  fi
  printf '%s개 커밋 · %s개 파일' "${commit_count}" "${file_count}"
}

now_epoch="$(date +%s)"
elapsed_seconds=$((now_epoch - started_epoch))
actor="${MM_ACTOR:-${GITLAB_USER_NAME:-${CI_COMMIT_AUTHOR:-확인 불가}}}"
completed_at="${MM_COMPLETED_AT:-$(TZ=Asia/Seoul date '+%m/%d %H:%M KST')}"
elapsed="${MM_DURATION_TEXT:-$(duration_text "${elapsed_seconds}")}"
changes="$(change_summary)"
service_url="${MM_SERVICE_URL:-${CI_ENVIRONMENT_URL:-${default_service_url}}}"

case "${event}" in
  success)
    heading=":small_green_circle: ${component_label} 배포 완료"
    time_label=완료
    description=
    mention=
    link_label="서비스 열기"
    ;;
  rolled_back)
    heading=":small_orange_circle: ${component_label} 배포 실패 · 자동 복구 완료"
    time_label=발생
    description="이전 정상 버전으로 자동 복구했습니다."
    mention=
    link_label="서비스 확인"
    ;;
  rollback_failed)
    heading=":small_red_circle: ${component_label} 배포 실패 · 자동 복구 실패"
    time_label=발생
    description="자동 복구에 실패했습니다. 즉시 서버 확인이 필요합니다."
    mention="@channel"$'\n\n'
    link_label="서비스 확인"
    ;;
  failed)
    heading=":small_red_circle: ${component_label} 배포 실패"
    time_label=발생
    description="배포가 완료되지 않았습니다. Job 로그를 확인해 주세요."
    mention="@channel"$'\n\n'
    link_label="서비스 확인"
    ;;
  integration_failed)
    heading=":small_yellow_circle: ${component_label} 통합 검증 실패"
    time_label=발생
    description="후보 버전이 현재 운영 조합과 맞지 않아 배포하지 않았습니다."
    mention=
    link_label="Job 로그 열기"
    service_url="${CI_JOB_URL:-${service_url}}"
    ;;
  jetson_published)
    heading=":small_blue_circle: Jetson 릴리스 게시 완료"
    time_label=완료
    description="Jetson이 다음 부팅 또는 갱신 주기에 이 버전을 확인합니다."
    mention=
    link_label="Manifest 열기"
    ;;
  connection_test)
    heading="Mattermost 알림 연결 확인"
    time_label=확인
    description="CI/CD 배포 알림 연결이 정상입니다."
    mention=
    link_label="서비스 열기"
    ;;
esac

message="# ${heading}"$'\n\n'
message+="${mention}"
message+="**담당자** ${actor}"$'\n\n'
message+="**변경 규모** ${changes}"$'\n\n'
message+="**${time_label} 시각** ${completed_at} · ${elapsed}"
if [ -n "${description}" ]; then
  message+=$'\n\n'"${description}"
fi
message+=$'\n\n'"[${link_label}](${service_url})"

payload="$(MM_MESSAGE="${message}" python3 - <<'PY'
import json
import os

print(json.dumps({"text": os.environ["MM_MESSAGE"]}, ensure_ascii=False))
PY
)"

if [ "${MM_NOTIFY_DRY_RUN:-false}" = true ]; then
  printf '%s\n' "${payload}"
  exit 0
fi

if [ -z "${MM_WEBHOOK_URL:-}" ]; then
  echo "Mattermost notification skipped: MM_WEBHOOK_URL is not set" >&2
  if [ "${MM_NOTIFY_STRICT:-false}" = true ]; then exit 1; else exit 0; fi
fi

if ! curl --fail --silent --show-error \
  --header 'Content-Type: application/json' \
  --data-binary "${payload}" \
  "${MM_WEBHOOK_URL}" >/dev/null; then
  echo "Mattermost notification failed; deployment result is unchanged" >&2
  if [ "${MM_NOTIFY_STRICT:-false}" = true ]; then exit 1; fi
fi
