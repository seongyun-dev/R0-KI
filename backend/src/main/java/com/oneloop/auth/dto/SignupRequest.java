package com.oneloop.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "회원가입 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class SignupRequest {
    @Schema(description = "로그인 아이디", example = "admin", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "아이디는 필수입니다.")
    @Size(max = 50, message = "아이디는 50자 이하여야 합니다.")
    private String username;

    @Schema(
            description = "로그인 비밀번호",
            example = "password123!",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "비밀번호는 필수입니다.")
    @Size(min = 8, max = 100, message = "비밀번호는 8자 이상 100자 이하여야 합니다.")
    private String password;

    @Schema(description = "사용자 이름", example = "홍길동", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "이름은 필수입니다.")
    @Size(max = 50, message = "이름은 50자 이하여야 합니다.")
    private String name;

    @Schema(
            description = "휴대전화 번호",
            example = "010-1234-5678",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "휴대전화 번호는 필수입니다.")
    @Size(max = 20, message = "휴대전화 번호는 20자 이하여야 합니다.")
    private String phoneNumber;

    @Schema(
            description = "이메일. 인증번호 확인을 마친 주소여야 한다.",
            example = "test@gmail.com",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "이메일은 필수입니다.")
    @Email(message = "이메일 형식이 올바르지 않습니다.")
    @Size(max = 255, message = "이메일은 255자 이하여야 합니다.")
    private String email;

    @Schema(description = "소속 아파트 단지", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "아파트 정보는 필수입니다.")
    @Valid
    private ApartmentRequest apartment;
}
