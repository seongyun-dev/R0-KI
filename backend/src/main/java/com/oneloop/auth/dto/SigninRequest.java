package com.oneloop.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "로그인 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class SigninRequest {

    @Schema(description = "로그인 아이디", example = "admin", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "아이디는 필수입니다.")
    @Size(max = 50, message = "아이디는 50자 이하여야 합니다.")
    private String username;

    @Schema(
            description = "로그인 비밀번호",
            example = "password123!",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "비밀번호는 필수입니다.")
    @Size(max = 100, message = "비밀번호는 100자 이하여야 합니다.")
    private String password;
}
