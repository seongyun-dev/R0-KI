package com.oneloop.event.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "판별할 차량 1건 (순찰 중 임시 기록된 좌표+번호판)")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VehicleCheckItemRequest {

    @Schema(description = "로봇이 순찰 중 임시로 붙인 식별자 - 응답의 violations에서 이 값으로 매칭", example = "v1")
    @NotBlank(message = "tempId는 필수입니다.")
    private String tempId;

    @Schema(description = "감지 위치 x좌표", example = "15.200")
    @NotNull(message = "x는 필수입니다.")
    private BigDecimal x;

    @Schema(description = "감지 위치 y좌표", example = "8.700")
    @NotNull(message = "y는 필수입니다.")
    private BigDecimal y;

    @Schema(description = "인식된 차량 번호판", example = "12가3456")
    @NotBlank(message = "licensePlate는 필수입니다.")
    private String licensePlate;

    @Schema(
            description = "이벤트 상세 원본 텍스트 (confidence= 값이 있으면 파싱해서 별도 저장)",
            example = "CAR, confidence=0.91",
            nullable = true)
    private String eventDetails;

    @Schema(description = "감지 시각", example = "2026-07-23T14:10:00+09:00")
    @NotNull(message = "occurredAt은 필수입니다.")
    private OffsetDateTime occurredAt;
}
