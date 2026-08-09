package com.oneloop.analytics.dto.response;

import com.oneloop.analytics.domain.AnalyticsInsightGenerationStatus;
import com.oneloop.analytics.domain.AnalyticsInsightPeriodType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

/**
 * AI 인사이트 조회 응답(data).
 *
 * <p>DB에 row가 없으면 generationStatus/insightContent는 null이다.
 * (Step 2: 조회만. 생성은 Step 3 Worker에서 처리)
 */
@Getter
@Builder
@Schema(description = "AI 인사이트 조회 응답")
public class AnalyticsInsightResponse {

    @Schema(description = "인사이트 ID. 캐시 row가 없으면 null", example = "1")
    private Long insightId;

    @Schema(description = "기간 유형", example = "WEEK")
    private AnalyticsInsightPeriodType periodType;

    @Schema(description = "기간 키", example = "2026-W30")
    private String periodKey;

    @Schema(description = "분석 시작 시각(KST)", example = "2026-07-20T00:00:00")
    private LocalDateTime periodFrom;

    @Schema(description = "분석 종료 시각(KST)", example = "2026-07-26T23:59:59.999999999")
    private LocalDateTime periodTo;

    @Schema(description = "시간대", example = "Asia/Seoul")
    private String timezone;

    @Schema(description = "생성 상태. row 없으면 null")
    private AnalyticsInsightGenerationStatus generationStatus;

    @Schema(description = "인사이트 본문. COMPLETED일 때만 값")
    private String insightContent;
}
