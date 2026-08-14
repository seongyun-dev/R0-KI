# OCR (`ai/ocr`)

번호판 인식(PaddleOCR TextRecognition) 파인튜닝 산출물입니다.

```
ocr/
├── models/ocr_finetune_rec/   # inference.json / .pdiparams / .yml
├── docs/models.md             # Acc 정의·데이터
└── scr/images/                # OCR crop 예시
```

| 항목 | 내용 |
|------|------|
| 베이스 | `korean_PP-OCRv5_mobile_rec` |
| Valid Acc | ≈ 0.93 (라인 완전일치) |

상세: [`docs/models.md`](docs/models.md)

상위 개요: [../README.md](../README.md)
