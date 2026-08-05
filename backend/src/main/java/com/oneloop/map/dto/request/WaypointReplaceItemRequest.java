package com.oneloop.map.dto.request;

import com.oneloop.map.domain.NavigationWaypointAction;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "순서가 있는 순찰 경로 지점")
public class WaypointReplaceItemRequest {

    @NotNull
    @Min(1)
    private Integer sequence;

    @NotNull
    @Digits(integer = 7, fraction = 3)
    private BigDecimal x;

    @NotNull
    @Digits(integer = 7, fraction = 3)
    private BigDecimal y;

    @NotNull private NavigationWaypointAction action;

    @Schema(description = "로봇 도착 방향(rad), 미지정 시 방향 제약 없음")
    @Digits(integer = 3, fraction = 4)
    private BigDecimal yaw;

    @DecimalMin(value = "0.20")
    @DecimalMax(value = "1.00")
    @Digits(integer = 2, fraction = 3)
    @Schema(description = "도착 허용 반경(m), 0.20~1.00, 미지정 시 0.30", example = "0.30")
    private BigDecimal acceptanceRadius;

    @Schema(description = "선택적 구역 참조 ID")
    private Long zoneId;
}
