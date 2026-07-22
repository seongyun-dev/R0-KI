package com.oneloop.robot.controller;

import com.oneloop.global.response.PageResponse;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.response.RobotDetailResponse;
import com.oneloop.robot.dto.response.RobotListResponse;
import com.oneloop.robot.dto.response.RobotRegisterResponse;
import com.oneloop.robot.dto.response.RobotStatsResponse;
import com.oneloop.robot.service.RobotService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
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
    public RobotRegisterResponse register(
            Authentication authentication, @Valid @RequestBody RobotRegisterRequest request) {
        return robotService.register(Long.valueOf(authentication.getName()), request);
    }

    // 로봇 목록 조회
    @GetMapping
    public PageResponse<RobotListResponse> list(
            Authentication authentication, @ParameterObject Pageable pageable) {
        return robotService.findAll(Long.valueOf(authentication.getName()), pageable);
    }

    // 로봇 현황 통계 조회
    @GetMapping("/stats")
    public RobotStatsResponse stats(Authentication authentication) {
        return robotService.getStats(Long.valueOf(authentication.getName()));
    }

    // 로봇 상세 조회
    @GetMapping("/{robotId}")
    public RobotDetailResponse detail(Authentication authentication, @PathVariable Long robotId) {
        return robotService.findById(Long.valueOf(authentication.getName()), robotId);
    }
}
