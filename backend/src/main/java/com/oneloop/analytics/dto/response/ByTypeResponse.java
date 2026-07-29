package com.oneloop.analytics.dto.response;

import com.oneloop.event.domain.EventType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

/**
 * by-type API 응답 본문(data).
 *
 * <p>프론트 차트 매핑 가이드:
 * - totalCount → 파이/막대 차트의 전체 기준
 * - items[].eventType / count → 유형별 막대/조각
 * - items[].ratio → 전체 대비 비율(%)
 * - items[].delta → 이전 동기간 대비 증감 표시
 *
 * <p>이벤트가 없으면 totalCount=0, items는 빈 배열이다.
 */
@Getter
@Builder
@Schema(description = "이벤트 유형별 통계 응답")
public class ByTypeResponse {

    @Schema(description = "조회 기간 전체 이벤트 수", example = "132")
    private long totalCount;

    @Schema(description = "유형별 집계 목록 (건수 내림차순)")
    private List<ByTypeItem> items;

    @Getter
    @Builder
    @Schema(description = "유형 1개의 통계")
    public static class ByTypeItem {

        @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
        private EventType eventType;

        @Schema(description = "현재 기간 발생 건수", example = "51")
        private long count;

        @Schema(description = "전체 대비 비율(%)", example = "38.64")
        private BigDecimal ratio;

        @Schema(description = "이전 동기간 대비 증감")
        private Delta delta;
    }

    @Getter
    @Builder
    @Schema(description = "이전 동기간 대비 증감")
    public static class Delta {

        @Schema(description = "현재 기간 건수", example = "51")
        private long current;

        @Schema(description = "이전 동기간 건수", example = "37")
        private long previous;

        @Schema(description = "증감 건수 (current - previous)", example = "14")
        private long diff;

        @Schema(description = "증감률(%)", example = "37.84")
        private BigDecimal changeRate;
    }
}
