package com.oneloop.event.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "위반으로 확정되어 이벤트가 생성된 차량 1건")
@Getter
@Builder
public class VehicleViolationResponse {
    @Schema(description = "요청 시 로봇이 붙인 임시 식별자", example = "v1")
    private String tempId;

    @Schema(description = "생성된 이벤트 ID", example = "101")
    private Long eventId;

    public static VehicleViolationResponse of(String tempId, Long eventId) {
        return VehicleViolationResponse.builder().tempId(tempId).eventId(eventId).build();
    }
}
