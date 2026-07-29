package com.oneloop.analytics.dto.response;

import com.oneloop.event.domain.EventType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

/**
 * overview API 응답 본문(data).
 *
 * <p>대시보드 상단 카드 매핑 가이드:
 * - totals.totalCount / todayCount → 건수 카드
 * - top.eventType / top.zone → "최다 유형", "최다 구역" 카드
 * - delta → 이전 기간 대비 증감 표시
 *
 * <p>이벤트가 없으면 totals는 0, top 필드는 null, byType은 빈 배열이다.
 */
@Getter
@Builder
@Schema(description = "이벤트 전체 현황 요약 응답")
public class OverviewResponse {

    @Schema(description = "조회 기간 정보")
    private Period period;

    @Schema(description = "전체/오늘 발생 건수")
    private Totals totals;

    @Schema(description = "최다 발생 유형/구역")
    private Top top;

    @Schema(description = "이전 동기간 대비 증감")
    private Delta delta;

    @Getter
    @Builder
    @Schema(description = "조회 기간")
    public static class Period {
        @Schema(description = "조회 시작 시각", example = "2026-07-01T00:00:00")
        private LocalDateTime from;

        @Schema(description = "조회 종료 시각", example = "2026-07-31T23:59:59")
        private LocalDateTime to;

        @Schema(description = "시간대", example = "Asia/Seoul")
        private String timezone;
    }

    @Getter
    @Builder
    @Schema(description = "요약 건수")
    public static class Totals {
        @Schema(description = "조회 기간 전체 이벤트 수", example = "132")
        private long totalCount;

        @Schema(description = "오늘 발생한 이벤트 수", example = "7")
        private long todayCount;
    }

    @Getter
    @Builder
    @Schema(description = "최다 항목")
    public static class Top {
        @Schema(description = "가장 많이 발생한 이벤트 유형", example = "ILLEGAL_PARKING", nullable = true)
        private EventType eventType;

        @Schema(description = "가장 많이 발생한 구역", nullable = true)
        private Zone zone;
    }

    @Getter
    @Builder
    @Schema(description = "구역 정보")
    public static class Zone {
        @Schema(description = "구역 ID", example = "12")
        private Long zoneId;

        @Schema(description = "구역 이름", example = "지상 주차장 A")
        private String zoneName;
    }

    @Getter
    @Builder
    @Schema(description = "증감 정보")
    public static class Delta {
        @Schema(description = "전체 건수 증감")
        private TotalDelta total;

        @Schema(description = "유형별 증감 목록")
        private List<TypeDelta> byType;
    }

    @Getter
    @Builder
    @Schema(description = "전체 건수 증감")
    public static class TotalDelta {
        @Schema(description = "현재 기간 건수", example = "132")
        private long current;

        @Schema(description = "이전 동기간 건수", example = "104")
        private long previous;

        @Schema(description = "증감 건수 (current - previous)", example = "28")
        private long diff;

        @Schema(description = "증감률(%)", example = "26.92")
        private BigDecimal changeRate;
    }

    @Getter
    @Builder
    @Schema(description = "유형별 증감")
    public static class TypeDelta {
        @Schema(description = "이벤트 유형", example = "ILLEGAL_PARKING")
        private EventType eventType;

        @Schema(description = "현재 기간 건수", example = "51")
        private long current;

        @Schema(description = "이전 동기간 건수", example = "37")
        private long previous;

        @Schema(description = "증감 건수", example = "14")
        private long diff;

        @Schema(description = "증감률(%)", example = "37.84")
        private BigDecimal changeRate;
    }
}
