package com.oneloop.event.dto.request;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.RiskLevel;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "이벤트 생성 요청 (로봇 → 백엔드)")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EventCreateRequest {

    @Schema(description = "이벤트 유형", example = "EMERGENCY")
    @NotNull(message = "eventType은 필수입니다.")
    private EventType eventType;

    @Schema(description = "이벤트 제목", example = "쓰러진 사람 감지")
    @NotBlank(message = "eventTitle은 필수입니다.")
    private String eventTitle;

    @Schema(
            description = "이벤트 상세 원본 텍스트 (confidence= 값이 있으면 파싱해서 별도 저장)",
            example = "LYING_PERSON, confidence=0.94",
            nullable = true)
    private String eventDetails;

    @Schema(description = "탐지 시각", example = "2026-07-23T14:15:30+09:00")
    @NotNull(message = "occurredAt은 필수입니다.")
    private OffsetDateTime occurredAt;

    @Schema(description = "발생 위치 x좌표", example = "12.350")
    @NotNull(message = "x는 필수입니다.")
    private BigDecimal x;

    @Schema(description = "발생 위치 y좌표", example = "7.860")
    @NotNull(message = "y는 필수입니다.")
    private BigDecimal y;

    @Schema(description = "위험도", example = "EMERGENCY")
    @NotNull(message = "riskLevel은 필수입니다.")
    private RiskLevel riskLevel;

    @Schema(description = "인식된 차량 번호판 (불법주차/미등록차량만)", example = "12가3456", nullable = true)
    private String recognizedLicensePlate;
}
