package com.oneloop.robot.controller;

import com.oneloop.global.response.PageResponse;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.response.RobotListResponse;
import com.oneloop.robot.dto.response.RobotResponse;
import com.oneloop.robot.service.RobotService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Pageable;
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
@RequestMapping("/api/robots")
public class RobotController {

    private final RobotService robotService;

    // 로봇 등록
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public RobotResponse register(
            Authentication authentication, @Valid @RequestBody RobotRegisterRequest request) {
        return robotService.register(Long.valueOf(authentication.getName()), request);
    }

    // 로봇 목록 조회
    @GetMapping
    public PageResponse<RobotListResponse> list(Authentication authentication, Pageable pageable) {
        return robotService.findAll(Long.valueOf(authentication.getName()), pageable);
    }
}
