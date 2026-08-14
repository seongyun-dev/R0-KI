# 프로젝트 협업 가이드

이 문서는 팀의 **Jira 운영**, **GitLab 브랜치 전략**, **Commit / Merge Request 규칙**, **CI/CD 흐름**을 정리한 공통 가이드입니다.

프로젝트 소개·기술 설명은 루트 [README.md](../README.md)를 참고하세요.

## 핵심 작업 흐름

모든 개발은 아래 순서로 진행합니다.

```text
Jira Story 생성
    ↓
Story Point / Sprint / 담당자 설정
    ↓
Jira에서 Create Branch
    ↓
feat 브랜치에서 개발
    ↓
Commit & Push
    ↓
Merge Request
    ↓
Code Review / CI 확인
    ↓
파트 dev Merge
    ↓
Jira Done
```

안정화 이후에는 다음 순서로 상위 브랜치에 반영합니다.

```text
feat
  ↓
파트 dev
  ↓
파트 master
  ↓
develop
  ↓
master
```

---

# 1. Jira 사용 규칙

## Issue 구조

```text
Epic
 └── Story
      └── Task (필요한 경우)
```

- **Epic**: 큰 기능 단위
- **Story**: 실제 구현할 기능 단위
- **Task**: Story 내부 작업을 별도로 관리할 때만 사용

### Epic 예시

```text
자율 순찰 주행
이벤트 및 알림 관리
통합 관제 대시보드
서비스 공통 기반 및 인증
```

### Story 제목 형식

```text
[파트] 기능명
```

예시:

```text
[BE] 이벤트 저장 API
[FE] 로그인 화면
[AI] 사람 탐지
[IoT] LiDAR 기반 2D 지도 생성
```

---

## Sprint 시작 시

1. Story 생성
2. Story Point 설정
3. 현재 Sprint에 등록
4. 담당자 지정
5. Jira에서 Create Branch

### Story Point

| Point | 기준 |
| ---: | --- |
| 1 | 매우 쉬움 |
| 2 | 쉬움 |
| 3 | 보통 |
| 5 | 어려움 |
| 8 | 매우 어려움 — Story 분리 권장 |

Story Point는 **작업량, 복잡도, 불확실성**을 함께 고려합니다.

Story 하나당 담당자 1명을 원칙으로 합니다.

---

## Jira 상태

```text
To Do
  ↓
In Progress
  ↓
Code Review
  ↓
Done
```

| 상태 | 변경 시점 |
| --- | --- |
| `To Do` | Story 생성 |
| `In Progress` | 개발 시작 |
| `Code Review` | Merge Request 생성 |
| `Done` | Merge 완료 |

---

# 2. GitLab 브랜치 전략

## 브랜치 구조

```text
master
│
└── develop
    │
    ├── frontend/master
    │   └── frontend/dev
    │       └── feat/E103-xxx-기능명
    │
    ├── backend/master
    │   └── backend/dev
    │       └── feat/E103-xxx-기능명
    │
    ├── ai/master
    │   └── ai/dev
    │       └── feat/E103-xxx-기능명
    │
    └── iot/master
        └── iot/dev
            └── feat/E103-xxx-기능명
```

---

## 브랜치 역할

### `feat/*`

실제 기능 개발 브랜치입니다.

형식:

```text
feat/{Jira번호}-{기능명}
```

예시:

```text
feat/E103-101-회원가입API
feat/E103-115-로그인화면
feat/E103-130-사람탐지
feat/E103-142-LiDAR2D지도
```

브랜치는 **Jira의 Create Branch 기능으로 생성하는 것을 원칙**으로 합니다.

---

### 파트 `dev`

파트의 기능 개발 결과를 모으는 브랜치입니다.

```text
frontend/dev
backend/dev
ai/dev
iot/dev
```

- Feature 브랜치 통합
- 기능 검증
- CI 실행
- 실제 서버 배포는 하지 않음

---

### 파트 `master`

파트별 안정 버전을 관리합니다.

```text
frontend/master
backend/master
ai/master
iot/master
```

- 파트 내부 테스트 완료
- CI 통과
- Code Review 완료
- 최소 1명 Approve 후 Merge

---

### `develop`

모든 파트의 안정 버전을 합치는 **전체 통합 브랜치**입니다.

```text
frontend/master ─┐
backend/master  ──┤
ai/master       ──┼──> develop
iot/master      ──┘
```

전체 통합 테스트를 진행합니다.

---

### `master`

최종 발표 및 배포 버전입니다.

- 전체 통합 완료
- 발표 가능한 상태
- 안정성이 검증된 버전만 반영

---

# 3. Commit 메시지 규칙

| Prefix | 용도 |
| --- | --- |
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 |
| `style` | 코드 스타일 수정 |
| `refactor` | 코드 구조 개선 |
| `test` | 테스트 코드 |
| `chore` | 빌드 및 설정 변경 |

예시:

```text
feat: 회원가입 API 구현
fix: 로그인 오류 수정
docs: README 수정
refactor: 인증 로직 개선
```

가능하면 하나의 Commit에는 하나의 목적만 담습니다.

---

# 4. Merge Request 규칙

모든 병합은 **Merge Request를 통해 진행**합니다.

```text
개발 완료
    ↓
Commit & Push
    ↓
Merge Request
    ↓
Code Review
    ↓
Approve
    ↓
Merge
```

공통 규칙:

- 보호 브랜치에 직접 Push하지 않습니다.
- Merge 전에 CI 결과를 확인합니다.
- 파트 `master` Merge에는 최소 1명의 Approve가 필요합니다.
- 리뷰 없이 직접 Merge하지 않습니다.
- Merge 완료 후 Jira Story를 `Done`으로 변경합니다.

---

# 5. 브랜치 보호 규칙

다음 브랜치는 직접 Push하지 않습니다.

```text
master
develop

frontend/master
frontend/dev

backend/master
backend/dev

ai/master
ai/dev

iot/master
iot/dev
```

모든 변경은 Merge Request로 반영합니다.

---

# 6. CI / CD 규칙

## `feat` → 파트 `dev`

**CI만 수행합니다.**

- 빌드 확인
- 테스트 실행
- 실행 가능 여부 확인
- 서버 배포 없음

---

## 파트 `dev` → 파트 `master`

안정화된 코드를 반영합니다.

기준:

- 기능 개발 완료
- 파트 내부 테스트 완료
- CI 통과
- Code Review 완료
- 최소 1명 Approve

CD가 적용된 파트는 파트 `master` Merge 후 자동 배포합니다.

---

## `develop` → `master`

전체 기능이 완료되고 통합 테스트까지 끝났을 때만 Merge합니다.

`master`는 최종 발표 및 배포 기준 브랜치로 사용합니다.

---

## 현재 CI / CD 적용 범위

현재 자동 CI / CD 적용:

```text
Frontend
Backend
```

AI는 추후 적용 예정입니다.

AI 파트의 모델, 코드, 설정 파일은 GitLab에서 함께 관리합니다.

IoT는 장비 및 실행 환경에 맞춰 별도로 배포합니다.

---

# 7. Git 기본 사용 방법

```bash
git fetch

git switch backend/dev
git pull

# Jira에서 브랜치 생성 권장
# 수동 생성 시
git switch -c feat/E103-123-로그인

git status

git add .
git commit -m "feat: 로그인 기능 구현"

git push -u origin feat/E103-123-로그인
```

이후 GitLab에서 다음 방향으로 Merge Request를 생성합니다.

```text
feat/E103-123-로그인
        ↓
backend/dev
```

자주 사용하는 명령어:

```bash
git fetch
git pull
git status
git branch
git switch 브랜치명
git add .
git commit -m "메시지"
git push
git log --oneline
```

---

# 8. 팀 공통 규칙

1. 모든 개발은 Jira Story 생성 후 시작합니다.
2. Story 제목은 `[파트] 기능명` 형식을 사용합니다.
3. Story Point, Sprint, 담당자를 지정합니다.
4. 브랜치는 Jira의 Create Branch 기능으로 생성합니다.
5. 기능 개발은 `feat/*` 브랜치에서 진행합니다.
6. 보호 브랜치에는 직접 Push하지 않습니다.
7. 모든 병합은 Merge Request로 진행합니다.
8. Merge Request 생성 후 Code Review를 진행합니다.
9. 파트 `master` Merge에는 최소 1명의 Approve가 필요합니다.
10. Merge 완료 후 Jira Story를 `Done`으로 변경합니다.
11. 최종 발표 및 배포 버전은 `master`에서 관리합니다.

---

## 한눈에 보기

```text
Jira Story
    ↓
feat/E103-xxx
    ↓
파트 dev          # 기능 통합 / CI
    ↓
파트 master       # 파트 안정 버전 / CD
    ↓
develop           # 전체 통합
    ↓
master            # 최종 발표 / 배포
```
