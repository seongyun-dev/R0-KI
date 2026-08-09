package com.oneloop.event.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "차량 판별 응답 - 위반 차량만 나열, 정상 차량은 포함되지 않음")
@Getter
@Builder
public class VehicleCheckResponse {
    @Schema(description = "위반으로 확정된 차량 목록")
    private List<VehicleViolationResponse> violations;

    public static VehicleCheckResponse of(List<VehicleViolationResponse> violations) {
        return VehicleCheckResponse.builder().violations(violations).build();
    }
}
