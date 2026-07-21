package com.oneloop.auth.controller;

import com.oneloop.auth.dto.CurrentMemberResponse;
import com.oneloop.auth.dto.SigninRequest;
import com.oneloop.auth.dto.SigninResponse;
import com.oneloop.auth.dto.SignupRequest;
import com.oneloop.auth.dto.SignupResponse;
import com.oneloop.auth.service.AuthService;
import com.oneloop.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    @Operation(summary = "회원가입", description = "회원과 소속 아파트 단지를 등록합니다.")
    @PostMapping("/signup")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<SignupResponse> signup(@Valid @RequestBody SignupRequest request) {
        return ApiResponse.success("회원가입이 완료되었습니다.", authService.signup(request));
    }

    @PostMapping("/signin")
    public ApiResponse<SigninResponse> signin(@Valid @RequestBody SigninRequest request) {
        return ApiResponse.success("로그인이 완료되었습니다.", authService.signin(request));
    }

    @GetMapping("/me")
    public ApiResponse<CurrentMemberResponse> getCurrentMember(Authentication authentication) {
        return ApiResponse.success(
                authService.getCurrentMember(Long.valueOf(authentication.getName())));
    }
}
