package com.oneloop.auth.controller;

import com.oneloop.auth.dto.CurrentMemberResponse;
import com.oneloop.auth.dto.SigninRequest;
import com.oneloop.auth.dto.SigninResponse;
import com.oneloop.auth.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    @PostMapping("/signin")
    public SigninResponse signin(@Valid @RequestBody SigninRequest request) {
        return authService.signin(request);
    }

    @GetMapping("/me")
    public CurrentMemberResponse getCurrentMember(Authentication authentication) {
        return authService.getCurrentMember(Long.valueOf(authentication.getName()));
    }
}
