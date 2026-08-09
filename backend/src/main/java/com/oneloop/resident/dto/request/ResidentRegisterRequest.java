package com.oneloop.resident.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "입주민 등록 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ResidentRegisterRequest {

    @Schema(description = "입주민 이름", example = "김입주", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "이름은 필수입니다.")
    @Size(max = 50, message = "이름은 50자 이하여야 합니다.")
    private String name;

    @Schema(
            description = "연락처 (숫자와 하이픈만)",
            example = "010-1234-5678",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "연락처는 필수입니다.")
    @Size(max = 20, message = "연락처는 20자 이하여야 합니다.")
    @Pattern(regexp = "^[0-9-]+$", message = "연락처는 숫자와 하이픈만 입력할 수 있습니다.")
    private String phoneNumber;

    @Schema(description = "동", example = "101", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "동은 필수입니다.")
    @Size(max = 20, message = "동은 20자 이하여야 합니다.")
    private String buildingNumber;

    @Schema(description = "호수", example = "1502", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "호수는 필수입니다.")
    @Size(max = 20, message = "호수는 20자 이하여야 합니다.")
    private String unitNumber;

    @Schema(description = "등록 차량 목록 (없이 등록 후 상세에서 추가할 수도 있다)")
    @Valid
    private List<VehicleRegisterRequest> vehicles;
}
