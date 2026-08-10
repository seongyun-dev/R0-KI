package com.oneloop.resident.dto.response;

import com.oneloop.resident.domain.RegisteredVehicle;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "등록 차량 응답")
public class RegisteredVehicleResponse {

    @Schema(description = "차량 ID", example = "1")
    private Long vehicleId;

    @Schema(description = "차량 번호", example = "12가3456")
    private String licensePlate;

    @Schema(description = "장애인 차량 여부", example = "false")
    private boolean disabledVehicle;

    public static RegisteredVehicleResponse from(RegisteredVehicle vehicle) {
        return RegisteredVehicleResponse.builder()
                .vehicleId(vehicle.getId())
                .licensePlate(vehicle.getLicensePlate())
                .disabledVehicle(vehicle.isDisabledVehicle())
                .build();
    }
}
