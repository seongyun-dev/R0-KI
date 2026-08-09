package com.oneloop.patrol.dto.response;

import com.oneloop.patrol.domain.AiSummaryGenerationStatus;
import com.oneloop.patrol.domain.PatrolAiSummary;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "AI 순찰 요약 응답")
public class PatrolAiSummaryResponse {
    @Schema(description = "AI 요약 생성 상태", example = "COMPLETED")
    private AiSummaryGenerationStatus generationStatus;

    @Schema(description = "AI 요약 내용", example = "해당 순찰에 대한 AI 요약 내용입니다.", nullable = true)
    private String summaryContent;

    public static PatrolAiSummaryResponse from(PatrolAiSummary aiSummary) {
        return PatrolAiSummaryResponse.builder()
                .generationStatus(aiSummary.getGenerationStatus())
                .summaryContent(aiSummary.getSummaryContent())
                .build();
    }
}
