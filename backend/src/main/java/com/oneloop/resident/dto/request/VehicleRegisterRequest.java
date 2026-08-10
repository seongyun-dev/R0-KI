package com.oneloop.resident.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "입주민 차량 등록 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VehicleRegisterRequest {

    @Schema(description = "차량 번호", example = "12가3456", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "차량 번호는 필수입니다.")
    @Size(max = 20, message = "차량 번호는 20자 이하여야 합니다.")
    private String licensePlate;

    @Schema(description = "장애인 차량 여부", example = "false")
    private boolean disabledVehicle;
}
