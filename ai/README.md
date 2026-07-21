# AI팀 Git 규칙

## 1. 분야별 브랜치

* YOLO: `ai/yolo`
* OCR: `ai/ocr`
* AI 보고서: `ai/report`

각 분야의 기능이 완성되면 해당 분야 브랜치를 `ai/dev` 브랜치에 병합합니다.

## 2. 개인 브랜치 생성 규칙

개인 작업 브랜치는 담당 분야 브랜치에서 생성합니다.

형식:

```text
ai/이니셜/모델/기능
```

예시:

```text
ai/msw/yolo/train
ai/msw/yolo/add-dataset
ai/msw/ocr/preprocess
ai/msw/report/create-prompt
```

작업이 완료되면 개인 브랜치를 해당 분야 브랜치에 병합합니다.

예시:

```text
ai/msw/yolo/train → ai/yolo
ai/msw/ocr/preprocess → ai/ocr
ai/msw/report/create-prompt → ai/report
```

## 3. 커밋 규칙

형식:

```text
이름_모델_기능 변경 내용
```

변경 내용은 한글로 짧고 명확하게 작성합니다.

예시:

```text
문성웅_yolo_train 번호판 탐지 모델 학습
문성웅_yolo_data 학습 데이터 추가
문성웅_ocr_preprocess 번호판 이미지 전처리
문성웅_report_prompt 보고서 프롬프트 수정
```

하나의 커밋에는 가능한 한 하나의 작업 내용만 포함합니다.
