package com.oneloop.event.controller;

import com.oneloop.event.dto.request.EvidenceUploadRequest;
import com.oneloop.event.dto.response.EvidenceUploadResponse;
import com.oneloop.event.service.EventCreationService;
import com.oneloop.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

// 로봇이 서비스 토큰으로 호출하는 증거자료 업로드 전용 컨트롤러.
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/events")
public class RobotEvidenceController {

    private final EventCreationService eventCreationService;

    @Operation(summary = "증거자료 업로드", description = "이벤트에 대한 사진 증거자료를 업로드합니다.")
    @PostMapping("/{eventId}/evidence")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<EvidenceUploadResponse> uploadEvidence(
            @AuthenticationPrincipal Long robotId,
            @Parameter(description = "이벤트 ID", example = "1", required = true) @PathVariable
                    Long eventId,
            @Valid @ModelAttribute EvidenceUploadRequest request) {
        return ApiResponse.success(
                "증거자료가 업로드되었습니다.",
                eventCreationService.uploadEvidence(robotId, eventId, request));
    }
}
