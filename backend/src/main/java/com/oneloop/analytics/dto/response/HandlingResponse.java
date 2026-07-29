package com.oneloop.analytics.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

/**
 * handling(처리 현황) API 응답 본문(data).
 *
 * <p>프론트 HandlingChart 매핑:
 * - items[].label → Y축 (전체 / 주차 / 쓰레기 / 위험구역)
 * - handled / pending → 건수
 * - handledPct / pendingPct → 100% 기준 막대
 *
 * <p>상태 정의:
 * - handled = COMPLETED
 * - pending = DETECTED + PROCESSING (완료 제외 = 아직 미처리)
 */
@Getter
@Builder
@Schema(description = "이벤트 처리 현황 응답")
public class HandlingResponse {

    @Schema(description = "라벨별 처리/미처리 집계 (전체 → 주차 → 쓰레기 → 위험구역 순)")
    private List<HandlingItem> items;

    @Getter
    @Builder
    @Schema(description = "한 라벨의 처리 현황")
    public static class HandlingItem {

        @Schema(description = "라벨", example = "전체")
        private String label;

        @Schema(description = "처리 완료 건수 (COMPLETED)", example = "59")
        private long handled;

        @Schema(description = "미처리 건수 (DETECTED + PROCESSING)", example = "24")
        private long pending;

        @Schema(description = "처리율(%)", example = "71.08")
        private BigDecimal handledPct;

        @Schema(description = "미처리율(%)", example = "28.92")
        private BigDecimal pendingPct;
    }
}
