# AI팀 Git 규칙

## 1. 분야별 브랜치

| 브랜치 | 담당 |
|--------|------|
| `ai/yolo` | YOLO 탐지 모델 |
| `ai/ocr` | 번호판 OCR |
| `ai/report` | AI 보고서·프롬프트 |
| `ai/dev` | 분야 병합·통합 데모(`pipeline/`) |

각 분야의 기능이 완성되면 해당 분야 브랜치를 **`ai/dev`에 병합**합니다.

## 2. 개인 브랜치 생성 규칙

개인 작업 브랜치는 **담당 분야 브랜치에서** 생성합니다.

형식:

```text
ai/이니셜/모델/기능
```

예시:

```text
ai/kim/yolo/train
ai/kim/yolo/add-dataset
ai/kim/ocr/preprocess
ai/kim/report/create-prompt
```

작업이 완료되면 개인 브랜치를 **해당 분야 브랜치에 병합**합니다.

```text
ai/kim/yolo/train          → ai/yolo
ai/kim/ocr/preprocess      → ai/ocr
ai/kim/report/create-prompt → ai/report
```

## 3. 커밋 규칙

형식:

```text
이름 모델 기능 변경 내용
```

변경 내용은 **한글로 짧고 명확하게** 작성합니다.  
하나의 커밋에는 가능한 한 **하나의 작업**만 포함합니다.

예시:

```text
kim yolo train 번호판 탐지 모델 학습
kim yolo data 학습 데이터 추가
kim ocr preprocess 번호판 이미지 전처리
kim report prompt 보고서 프롬프트 수정
```

## 4. 폴더와 브랜치 대응

| 브랜치 | 주로 수정하는 경로 |
|--------|-------------------|
| `ai/yolo` | `yolo/` |
| `ai/ocr` | `ocr/` |
| `ai/report` | `report/` |
| `ai/dev` | `pipeline/`, 루트 `README.md`, `requirements.txt`, `scr/gifs/` |
