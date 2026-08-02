#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
notify_script="${repository_root}/infra/scripts/notify-mattermost.sh"
common_env=(
  MM_NOTIFY_DRY_RUN=true
  MM_ACTOR=홍길동
  MM_CHANGE_SUMMARY="4개 커밋 · 17개 파일"
  MM_COMPLETED_AT="07/23 10:11 KST"
  MM_DURATION_TEXT="1분 24초"
  MM_SERVICE_URL=https://i15e103.p.ssafy.io
)

success_payload="$(env "${common_env[@]}" bash "${notify_script}" success frontend 0)"
MM_TEST_PAYLOAD="${success_payload}" python3 - <<'PY'
import json
import os
import sys

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# :small_green_circle: Frontend 배포 완료")
assert "**담당자** 홍길동" in text
assert "**변경 규모** 4개 커밋 · 17개 파일" in text
assert "**완료 시각** 07/23 10:11 KST · 1분 24초" in text
assert "[서비스 열기](https://i15e103.p.ssafy.io)" in text
assert "MM_WEBHOOK_URL" not in text
PY

rollback_payload="$(env "${common_env[@]}" bash "${notify_script}" rolled_back backend 0)"
MM_TEST_PAYLOAD="${rollback_payload}" python3 - <<'PY'
import json
import os
import sys

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# :small_orange_circle: Backend 배포 실패 · 자동 복구 완료")
assert "이전 정상 버전으로 자동 복구했습니다." in text
assert "@channel" not in text
PY

rollback_failed_payload="$(env "${common_env[@]}" bash "${notify_script}" rollback_failed backend 0)"
MM_TEST_PAYLOAD="${rollback_failed_payload}" python3 - <<'PY'
import json
import os
import sys

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# :small_red_circle: Backend 배포 실패 · 자동 복구 실패")
assert "@channel" in text
assert "즉시 서버 확인이 필요합니다." in text
PY

failed_payload="$(env "${common_env[@]}" bash "${notify_script}" failed backend 0)"
MM_TEST_PAYLOAD="${failed_payload}" python3 - <<'PY'
import json
import os

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# :small_red_circle: Backend 배포 실패")
assert "@channel" in text
PY

integration_payload="$(env "${common_env[@]}" CI_JOB_URL=https://gitlab.example/job/1 \
  bash "${notify_script}" integration_failed frontend 0)"
MM_TEST_PAYLOAD="${integration_payload}" python3 - <<'PY'
import json
import os

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# :small_yellow_circle: Frontend 통합 검증 실패")
assert "배포하지 않았습니다." in text
assert "[Job 로그 열기](https://gitlab.example/job/1)" in text
PY

jetson_payload="$(env "${common_env[@]}" bash "${notify_script}" jetson_published jetson 0)"
MM_TEST_PAYLOAD="${jetson_payload}" python3 - <<'PY'
import json
import os

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# :small_blue_circle: Jetson IoT 릴리스 게시 완료")
assert "AI baseline은 변경하지 않습니다." in text
PY

connection_payload="$(env "${common_env[@]}" bash "${notify_script}" connection_test all 0)"
MM_TEST_PAYLOAD="${connection_payload}" python3 - <<'PY'
import json
import os

text = json.loads(os.environ["MM_TEST_PAYLOAD"])["text"]
assert text.startswith("# Mattermost 알림 연결 확인")
assert "**확인 시각** 07/23 10:11 KST · 1분 24초" in text
assert "CI/CD 배포 알림 연결이 정상입니다." in text
PY

if MM_NOTIFY_STRICT=true MM_WEBHOOK_URL= bash "${notify_script}" connection_test all 0 >/dev/null 2>&1; then
  echo "Strict notification mode accepted a missing webhook URL" >&2
  exit 1
fi

echo "Mattermost notification tests passed"
