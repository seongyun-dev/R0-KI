package com.oneloop.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "로그인 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class SigninResponse {

    @Schema(
            description = "API 인증에 사용하는 JWT Access Token",
            example = "eyJhbGciOiJIUzI1NiJ9...",
            requiredMode = Schema.RequiredMode.REQUIRED)
    private String accessToken;

    @Schema(description = "로그인한 회원의 이름", example = "홍길동")
    private String name;

    @Schema(description = "소속 단지의 등록된 로봇 존재 여부", example = "true")
    private boolean hasRobot;

    @Schema(description = "소속 단지의 등록된 지도 존재 여부", example = "false")
    private boolean hasMap;
}
