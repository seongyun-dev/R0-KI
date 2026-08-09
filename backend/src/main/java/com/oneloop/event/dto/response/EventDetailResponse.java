package com.oneloop.event.dto.response;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.domain.RiskLevel;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "이벤트 상세 조회 응답")
public class EventDetailResponse {
    @Schema(description = "이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
    private EventType type;

    @Schema(description = "탐지 신뢰도", example = "0.987", nullable = true)
    private BigDecimal confidence;

    @Schema(description = "탐지 시각", example = "2026-07-15T09:12:00")
    private LocalDateTime occurredAt;

    @Schema(description = "경과 시간(초) - 처리완료 전에만 값 존재, 프론트에서 실시간 표시용", example = "720", nullable = true)
    private Long elapsedSeconds;

    @Schema(description = "처리완료 시각 - 처리완료된 경우에만 값 존재", example = "2026-07-15T09:30:00", nullable = true)
    private LocalDateTime processedAt;

    @Schema(description = "발생 위치가 속한 체크포인트 이름 (매칭되는 구역이 없으면 null)", example = "주차장", nullable = true)
    private String location;

    @Schema(description = "탐지 로봇 이름", example = "순찰로봇 1호")
    private String robotName;

    @Schema(description = "위험도", example = "NORMAL")
    private RiskLevel riskLevel;

    @Schema(description = "처리 상태", example = "DETECTED")
    private ProcessingStatus status;

    @Schema(description = "처리 메모 - 처리완료된 경우에만 값 존재", example = "차주 연락 후 이동 조치", nullable = true)
    private String processingNote;

    @Schema(description = "인식된 차량 번호판 (주차/차량 관련 이벤트가 아니면 null)", example = "12가3456", nullable = true)
    private String licensePlateNumber;

    @Schema(description = "증거자료 (없으면 null)", nullable = true)
    private EventEvidenceResponse evidence;

    public static EventDetailResponse of(
            DetectedEvent event,
            String location,
            Long elapsedSeconds,
            String processingNote,
            EventEvidenceResponse evidence) {
        return EventDetailResponse.builder()
                .eventId(event.getId())
                .type(event.getType())
                .confidence(event.getConfidence())
                .occurredAt(event.getOccurredAt())
                .elapsedSeconds(elapsedSeconds)
                .processedAt(event.getProcessedAt())
                .location(location)
                .robotName(event.getRobot().getName())
                .riskLevel(event.getRiskLevel())
                .status(event.getProcessingStatus())
                .processingNote(processingNote)
                .licensePlateNumber(event.getRecognizedLicensePlate())
                .evidence(evidence)
                .build();
    }
}
