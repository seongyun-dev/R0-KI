# YOLO (`ai/yolo`)

YOLO 탐지 모델 체크포인트·문서·탐지 예시입니다.

```
yolo/
├── checkpoints/     # v1 / v2 / v3
├── docs/models.md   # 지표·데이터·클래스
└── scr/images/      # 탐지 예시 이미지
```

| 버전 | 경로 | 비고 |
|------|------|------|
| v3 (권장) | `checkpoints/v3/best.pt` | mAP50 ≈ 0.86 |
| v2 | `checkpoints/v2/best.pt` | |
| v1 | `checkpoints/v1/best.pt` | |

상세: [`docs/models.md`](docs/models.md)

개인 브랜치 예: `ai/<이니셜>/yolo/<기능>` → 완료 후 `ai/yolo`에 병합.
