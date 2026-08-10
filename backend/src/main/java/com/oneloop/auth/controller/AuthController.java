package com.oneloop.auth.controller;

import com.oneloop.auth.dto.CurrentMemberResponse;
import com.oneloop.auth.dto.EmailSendRequest;
import com.oneloop.auth.dto.EmailVerifyRequest;
import com.oneloop.auth.dto.SigninRequest;
import com.oneloop.auth.dto.SigninResponse;
import com.oneloop.auth.dto.SignupRequest;
import com.oneloop.auth.dto.SignupResponse;
import com.oneloop.auth.service.AuthService;
import com.oneloop.auth.service.EmailVerificationService;
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
    private final EmailVerificationService emailVerificationService;

    @Operation(summary = "회원가입", description = "회원과 소속 아파트 단지를 등록합니다.")
    @PostMapping("/signup")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<SignupResponse> signup(@Valid @RequestBody SignupRequest request) {
        return ApiResponse.success("회원가입이 완료되었습니다.", authService.signup(request));
    }

    @Operation(
            summary = "이메일 인증번호 발송",
            description = "가입 가능한 이메일이면 6자리 인증번호를 보낸다. 이미 가입된 이메일이면 보내지 않는다.")
    @PostMapping("/email/send")
    public ApiResponse<Void> sendEmailVerification(@Valid @RequestBody EmailSendRequest request) {
        emailVerificationService.send(request.getEmail());
        return ApiResponse.success("EMAIL_VERIFICATION_SENT", "인증번호가 발송되었습니다.", null);
    }

    @Operation(summary = "이메일 인증번호 확인", description = "발송한 인증번호가 맞는지 확인하고 인증 완료로 표시한다.")
    @PostMapping("/email/verify")
    public ApiResponse<Void> verifyEmail(@Valid @RequestBody EmailVerifyRequest request) {
        emailVerificationService.verify(request.getEmail(), request.getCode());
        return ApiResponse.success("EMAIL_VERIFIED", "이메일 인증이 완료되었습니다.", null);
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
