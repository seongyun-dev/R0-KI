package com.oneloop.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "회원가입 아파트 단지 정보")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class ApartmentRequest {
    @Schema(
            description = "아파트 단지 이름",
            example = "원루프 아파트",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "아파트 이름은 필수입니다.")
    @Size(max = 100, message = "아파트 이름은 100자 이하여야 합니다.")
    private String name;

    @Schema(description = "우편번호", example = "06236", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "우편번호는 필수입니다.")
    @Size(max = 10, message = "우편번호는 10자 이하여야 합니다.")
    private String postalCode;

    @Schema(
            description = "아파트 주소",
            example = "서울특별시 강남구 테헤란로 212",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "아파트 주소는 필수입니다.")
    @Size(max = 200, message = "아파트 주소는 200자 이하여야 합니다.")
    private String address;
}
