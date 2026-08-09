package com.oneloop.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "이메일 인증번호 발송 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class EmailSendRequest {

    @Schema(
            description = "인증번호를 받을 이메일",
            example = "test@gmail.com",
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "이메일은 필수입니다.")
    @Email(message = "이메일 형식이 올바르지 않습니다.")
    @Size(max = 255, message = "이메일은 255자 이하여야 합니다.")
    private String email;
}
