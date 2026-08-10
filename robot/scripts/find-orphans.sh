#!/usr/bin/env bash
# 참조가 사라진 모듈과 설정을 찾는다.
#
# 왜 필요한가: 수정이 쌓이면서 대체된 코드가 지워지지 않고 남는다. 남은 코드는
# 읽는 사람에게 "이것도 살아 있다"는 잘못된 신호를 주고, 다음 사람이 그걸 근거로
# 판단하게 만든다.
#
# 왜 파이썬 import 만 보면 안 되는가: 2026-08-07 에 import 만 기준으로 세었다가
# src/aiot_robot/ai_runtime.py 를 고아로 분류했다. 그 파일은 infra/jetson/aiot-ai.service
# 가 직접 실행하는 진입점이다. 지웠으면 AI 서비스가 죽었다. 그래서 여기서는
# 셸 스크립트, systemd 유닛, YAML, 문서까지 전부 훑는다.
#
# 출력은 등급으로 나눈다. 등급이 곧 판단이 아니라 판단의 재료다:
#   [고아]      어디에서도 참조되지 않음        -> 지울 근거가 가장 강하다
#   [문서만]    코드는 안 쓰고 문서만 언급       -> 지우려면 문서도 같이 고쳐라
#   [테스트만]  자기 테스트 외에 소비자가 없음   -> 기능과 테스트를 함께 판단하라
#
# 사용: bash robot/scripts/find-orphans.sh [--quiet]
# 종료코드: 항상 0. 이 스크립트는 판정하지 않고 보고만 한다.

set -uo pipefail
robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(cd "${robot_root}/.." && pwd)"
cd "${robot_root}"

quiet=false
[ "${1:-}" = "--quiet" ] && quiet=true

search_roots=(. "${repo_root}/infra")
includes=(
  --include='*.py' --include='*.sh' --include='*.bash' --include='*.ps1'
  --include='*.service' --include='*.path' --include='*.timer'
  --include='*.yaml' --include='*.yml' --include='*.toml' --include='*.cfg'
  --include='*.xml' --include='*.md' --include='*.txt' --include='*.env.example'
)

orphan=(); docs_only=(); test_only=()

while IFS= read -r file; do
  module="$(basename "${file}" .py)"
  # __init__ 은 패키지 구성요소라 이름으로 추적할 수 없다.
  [ "${module}" = "__init__" ] && continue

  mapfile -t hits < <(
    grep -rl "${includes[@]}" -e "\b${module}\b" "${search_roots[@]}" 2>/dev/null \
      | sed 's|^\./||' | grep -v "^${file#./}$" | sort -u
  )
  [ "${#hits[@]}" -eq 0 ] && { orphan+=("${file}"); continue; }

  # 자기 자신을 대상으로 하는 테스트만 남았는지, 문서만 남았는지 가른다.
  non_doc=0; non_test=0
  for hit in "${hits[@]}"; do
    case "${hit}" in
      *.md|docs/*) continue ;;
    esac
    non_doc=$((non_doc + 1))
    case "$(basename "${hit}")" in
      test_*|*_test.py) continue ;;
    esac
    non_test=$((non_test + 1))
  done
  if [ "${non_doc}" -eq 0 ]; then docs_only+=("${file}")
  elif [ "${non_test}" -eq 0 ]; then test_only+=("${file}"); fi
done < <(find . -name '*.py' -not -path './.venv/*' -not -path '*/__pycache__/*' \
           -not -name 'test_*' | sort)

report() {
  local label="$1"; shift
  [ "$#" -eq 0 ] && return 0
  printf '\n%s (%d)\n' "${label}" "$#"
  for item in "$@"; do
    printf '  %-58s %s줄\n' "${item#./}" "$(wc -l < "${item}")"
  done
}

if [ "${quiet}" = false ]; then
  # ${arr[@]:-} 는 빈 배열을 빈 문자열 하나로 펼쳐 0건을 1건으로 세게 만든다.
  report '[고아] 어디에서도 참조되지 않음' ${orphan[@]+"${orphan[@]}"}
  report '[문서만] 코드는 쓰지 않음' ${docs_only[@]+"${docs_only[@]}"}
  report '[테스트만] 자기 테스트 외 소비자 없음' ${test_only[@]+"${test_only[@]}"}
fi

# 코드가 읽지 않는 환경변수. 예시 파일이 실제와 어긋나면 새 장비를
# 그 예시로 프로비저닝했을 때 조용히 잘못 뜬다.
dead_env=()
while IFS= read -r name; do
  n="$(grep -rl "${includes[@]}" -e "${name}" "${search_roots[@]}" 2>/dev/null \
        | grep -v 'env.example' | wc -l)"
  [ "${n}" -eq 0 ] && dead_env+=("${name}")
done < <(grep -hoE '^[A-Z][A-Z0-9_]*=' config/*.env.example 2>/dev/null | tr -d '=' | sort -u)

if [ "${quiet}" = false ] && [ "${#dead_env[@]}" -gt 0 ]; then
  printf '\n[사용되지 않는 환경변수] (%d)\n' "${#dead_env[@]}"
  printf '  %s\n' "${dead_env[@]}"
fi

printf '\n합계: 고아 %d / 문서만 %d / 테스트만 %d / 미사용 env %d\n' \
  "${#orphan[@]}" "${#docs_only[@]}" "${#test_only[@]}" "${#dead_env[@]}"
