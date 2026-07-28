package com.oneloop.event.dto.request;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.RiskLevel;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "일괄 생성할 이벤트 1건 (쓰레기탐지·분리수거장포화 전용)")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EventBatchItemRequest {

    @Schema(description = "로봇이 순찰 중 임시로 붙인 식별자 - 응답에서 이 값으로 eventId를 매칭", example = "e1")
    @NotBlank(message = "tempId는 필수입니다.")
    private String tempId;

    @Schema(description = "이벤트 유형", example = "TRASH_DETECTED")
    @NotNull(message = "eventType은 필수입니다.")
    private EventType eventType;

    @Schema(description = "이벤트 제목", example = "쓰레기 발견")
    @NotBlank(message = "eventTitle은 필수입니다.")
    private String eventTitle;

    @Schema(
            description = "이벤트 상세 원본 텍스트 (confidence= 값이 있으면 파싱해서 별도 저장)",
            example = "TRASH, confidence=0.91",
            nullable = true)
    private String eventDetails;

    @Schema(description = "탐지 시각", example = "2026-07-23T14:12:00")
    @NotNull(message = "occurredAt은 필수입니다.")
    private LocalDateTime occurredAt;

    @Schema(description = "발생 위치 x좌표", example = "3.200")
    @NotNull(message = "x는 필수입니다.")
    private BigDecimal x;

    @Schema(description = "발생 위치 y좌표", example = "6.900")
    @NotNull(message = "y는 필수입니다.")
    private BigDecimal y;

    @Schema(description = "위험도", example = "LOW")
    @NotNull(message = "riskLevel은 필수입니다.")
    private RiskLevel riskLevel;
}
