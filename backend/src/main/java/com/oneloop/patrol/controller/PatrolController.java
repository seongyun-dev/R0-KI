package com.oneloop.patrol.controller;

import com.oneloop.global.response.ApiResponse;
import com.oneloop.global.response.PageResponse;
import com.oneloop.global.security.CustomUserDetails;
import com.oneloop.patrol.dto.request.PatrolPeriodFilter;
import com.oneloop.patrol.dto.request.PatrolStartRequest;
import com.oneloop.patrol.dto.request.PatrolStatusFilter;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.dto.response.PatrolListResponse;
import com.oneloop.patrol.dto.response.PatrolStartResponse;
import com.oneloop.patrol.dto.response.PatrolStopResponse;
import com.oneloop.patrol.service.PatrolCommandService;
import com.oneloop.patrol.service.PatrolPdfService;
import com.oneloop.patrol.service.PatrolService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.data.domain.Sort.Direction.DESC;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/patrols")
public class PatrolController {

    private final PatrolService patrolService;
    private final PatrolCommandService patrolCommandService;
    private final PatrolPdfService patrolPdfService;

    @Operation(summary = "순찰 시작", description = "지정한 로봇에 순찰 시작 명령을 전송합니다.")
    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ApiResponse<PatrolStartResponse> start(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Valid @RequestBody PatrolStartRequest request) {
        return ApiResponse.success(
                "순찰이 요청되었습니다.",
                patrolCommandService.start(principal.getApartmentComplexId(), request));
    }

    @Operation(summary = "순찰 수동 종료", description = "진행 중인 순찰의 로봇에 STOP_PATROL 명령을 전송합니다.")
    @PostMapping("/{patrolId}/stop")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ApiResponse<PatrolStopResponse> stop(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "순찰 ID", example = "1", required = true) @PathVariable
                    Long patrolId) {
        return ApiResponse.success(
                "순찰 종료를 요청했습니다.",
                patrolCommandService.stop(principal.getApartmentComplexId(), patrolId));
    }

    @Operation(
            summary = "순찰 목록 조회",
            description = "소속 단지의 순찰 기록을 기간과 상태로 필터링하여 최신순으로 조회합니다.")
    @GetMapping
    public ApiResponse<PageResponse<PatrolListResponse>> list(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "기간 필터", example = "ALL")
                    @RequestParam(defaultValue = "ALL")
                    PatrolPeriodFilter period,
            @Parameter(description = "순찰 상태 필터", example = "ALL")
                    @RequestParam(defaultValue = "ALL")
                    PatrolStatusFilter status,
            @ParameterObject
                    @PageableDefault(size = 20, sort = "startedAt", direction = DESC)
                    Pageable pageable) {
        return ApiResponse.success(
                patrolService.findAll(
                        principal.getApartmentComplexId(), period, status, pageable));
    }

    @Operation(summary = "순찰 상세 조회", description = "순찰 경로, 배터리, 감지 이벤트 타임라인과 AI 요약을 조회합니다.")
    @GetMapping("/{patrolId}")
    public ApiResponse<PatrolDetailResponse> detail(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "순찰 ID", example = "1", required = true) @PathVariable
                    Long patrolId) {
        return ApiResponse.success(
                patrolService.findDetail(principal.getApartmentComplexId(), patrolId));
    }

    @Operation(summary = "순찰 보고서 PDF 다운로드", description = "순찰 상세 내용을 PDF 보고서로 다운로드합니다.")
    @GetMapping(value = "/{patrolId}/pdf", produces = MediaType.APPLICATION_PDF_VALUE)
    public ResponseEntity<byte[]> downloadPdf(
            @AuthenticationPrincipal CustomUserDetails principal,
            @Parameter(description = "순찰 ID", example = "1", required = true) @PathVariable
                    Long patrolId) {
        byte[] pdf = patrolPdfService.generate(principal.getApartmentComplexId(), patrolId);
        ContentDisposition disposition =
                ContentDisposition.attachment()
                        .filename("patrol-report-" + patrolId + ".pdf")
                        .build();

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .contentLength(pdf.length)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .body(pdf);
    }
}
