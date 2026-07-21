# GPU Device3 GitLab Runner

GPU 서버 `70.12.130.103`, 계정 `i15e103`, 할당 장치 `Device3`에 프로젝트 전용 Shell Runner를 두기 위한 절차다. HTTP URL만 확인된 상태이므로 SSH·sudo 접근이 확보되기 전에는 서버 변경을 시도하지 않는다. Runner 인증 토큰은 문서, 명령 기록, Git에 남기지 않는다.

## 1. 변경 전 환경 확인

GPU 서버 터미널에서 다음 정보를 먼저 기록한다.

```bash
uname -a
cat /etc/os-release
nvidia-smi -L
nvidia-smi --id=3 --query-gpu=index,uuid,name,driver_version,memory.total --format=csv,noheader
command -v nvcc >/dev/null && nvcc --version || true
python3 --version
python3 - <<'PY'
try:
    import torch
    print("torch", torch.__version__)
    print("cuda", torch.version.cuda)
    print("available", torch.cuda.is_available())
except ImportError:
    print("torch not installed")
PY
```

이 단계에서는 CUDA·TensorRT 버전을 추측하거나 설치하지 않는다. AI 코드의 실제 요구 버전과 JetPack 6.2 호환 조건을 확인한 뒤 설치한다.

## 2. 프로젝트 Runner 생성

GitLab 프로젝트의 **Settings > CI/CD > Runners**에서 project runner를 만든다.

- tag: `ai-gpu-device3`
- Run untagged jobs: off
- Lock to current project: on
- Protected: on
- 최대 timeout: 학습 시간에 맞게 설정

GitLab이 발급한 `glrt-` 형식 authentication token은 GPU 서버의 대화형 shell에서만 사용한다. 공식 GitLab 저장소를 추가한 후 `gitlab-runner` 패키지를 설치하고 다음과 같이 등록한다.

```bash
read -rsp 'Runner authentication token: ' RUNNER_AUTHENTICATION_TOKEN
echo
sudo gitlab-runner register \
  --non-interactive \
  --url 'https://lab.ssafy.com' \
  --token "${RUNNER_AUTHENTICATION_TOKEN}" \
  --executor shell \
  --description 'S15P11E103 GPU Device3'
unset RUNNER_AUTHENTICATION_TOKEN
```

새 authentication-token workflow에서는 tag, protected, locked, untagged 설정을 GitLab UI에서 관리한다. 설치·등록 방법은 [GitLab Runner Linux install](https://docs.gitlab.com/runner/install/linux-repository/)과 [runner creation workflow](https://docs.gitlab.com/ci/runners/new_creation_workflow/)를 기준으로 한다.

## 3. 동시 실행 제한

GPU 서버가 이 프로젝트 전용이면 `/etc/gitlab-runner/config.toml`의 전역 `concurrent`를 1로 둔다. 다른 프로젝트 Runner가 함께 있으면 전역값을 임의로 바꾸지 않고 GitLab의 `resource_group: ai-gpu-device3`로 이 프로젝트 학습·변환 job을 직렬화한다.

```bash
sudo gitlab-runner verify
sudo systemctl enable --now gitlab-runner
sudo systemctl status gitlab-runner --no-pager
```

Shell executor는 `gitlab-runner` 사용자의 권한으로 프로젝트 코드를 직접 실행한다. 따라서 이 Runner에는 protected job만 할당하고, 개인 프로젝트나 untrusted fork를 연결하지 않는다. 자세한 보안 특성은 [GitLab Shell executor 문서](https://docs.gitlab.com/runner/executors/shell/)를 따른다.

## 4. Device3 고정

초기 CI는 `CUDA_VISIBLE_DEVICES=3`으로 물리 Device3만 노출한다. CUDA 프로세스 내부에서는 이 장치가 논리 device 0으로 다시 번호가 매겨진다. 장치 순서 변경에 대비해 `nvidia-smi -L`의 UUID를 확인한 뒤 protected CI/CD 변수 `AI_GPU_SELECTOR=GPU-...`로 전환하는 것을 권장한다.

GPU 노출 방식은 [NVIDIA CUDA environment variables](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/environment-variables.html)의 `CUDA_VISIBLE_DEVICES` 계약을 따른다.

## 5. 검증 순서

1. Web pipeline에서 `gpu_environment`를 수동 실행한다.
2. 출력에 물리 Device3의 UUID·driver와 Python 환경만 남고 secret이 없는지 확인한다.
3. AI 팀이 `ai/scripts/train.sh`와 출력 경로 `ai/artifacts/training/`을 제공한 뒤 `ai_train`을 실행한다.
4. 변환 계약이 준비되면 `ai_convert`를 실행하고 `ai/artifacts/converted/`의 모델·manifest·checksum을 확인한다.
5. 승인된 모델만 `jetson-vX.Y.Z` release에 포함한다.

Runner가 없거나 offline이면 일반 EC2 CI는 계속 동작하고 GPU manual job만 pending 상태가 된다.
