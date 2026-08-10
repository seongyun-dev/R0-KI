package com.oneloop.event.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "차량 판별 요청 (로봇 → 백엔드, 순찰 종료 시점 일괄 전송)")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VehicleCheckRequest {

    @Schema(description = "판별할 차량 목록")
    @NotEmpty(message = "vehicles는 최소 1건 이상이어야 합니다.")
    @Valid
    private List<VehicleCheckItemRequest> vehicles;
}
