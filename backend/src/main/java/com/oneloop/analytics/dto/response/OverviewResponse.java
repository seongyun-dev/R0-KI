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
 * <p>대시보드 KPI/카드 매핑 가이드:
 * - totals.totalCount / todayCount → 이벤트 건수
 * - totals.patrolCount → 총 순찰 횟수 (COMPLETED만)
 * - totals.avgHandleMin → 평균 처리시간(분)
 * - top.eventType / top.zone → 최다 유형/구역
 * - delta.total / patrol / handleTime → 이전 동기간 대비 증감
 *
 * <p>이벤트가 없으면 totals 건수는 0, top은 null, byType은 빈 배열.
 * 완료 이벤트(processedAt 있음)가 없으면 avgHandleMin은 null.
 */
@Getter
@Builder
@Schema(description = "이벤트 전체 현황 요약 응답")
public class OverviewResponse {

    @Schema(description = "조회 기간 정보")
    private Period period;

    @Schema(description = "전체/오늘 발생 건수 + KPI")
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
    @Schema(description = "요약 건수 / KPI")
    public static class Totals {
        @Schema(description = "조회 기간 전체 이벤트 수", example = "132")
        private long totalCount;

        @Schema(description = "오늘 발생한 이벤트 수", example = "7")
        private long todayCount;

        @Schema(
                description = "조회 기간 완료 순찰 수 (patrol_status=COMPLETED, startedAt 기준)",
                example = "42")
        private long patrolCount;

        @Schema(
                description =
                        "평균 처리시간(분). COMPLETED 이고 processedAt이 있는 이벤트만 "
                                + "(processedAt - occurredAt). 대상 없으면 null",
                example = "12.5",
                nullable = true)
        private BigDecimal avgHandleMin;
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
    @Schema(description = "구역 정보 (checkpoint_id 기준)")
    public static class Zone {
        @Schema(description = "구역 ID (= checkpoint_id)", example = "12")
        private Long zoneId;

        @Schema(description = "구역 이름", example = "지상 주차장 A")
        private String zoneName;
    }

    @Getter
    @Builder
    @Schema(description = "증감 정보")
    public static class Delta {
        @Schema(description = "전체 이벤트 건수 증감")
        private TotalDelta total;

        @Schema(description = "완료 순찰 수 증감")
        private TotalDelta patrol;

        @Schema(description = "평균 처리시간(분) 증감", nullable = true)
        private DecimalDelta handleTime;

        @Schema(description = "유형별 증감 목록")
        private List<TypeDelta> byType;
    }

    @Getter
    @Builder
    @Schema(description = "정수 지표 증감")
    public static class TotalDelta {
        @Schema(description = "현재 기간 값", example = "132")
        private long current;

        @Schema(description = "이전 동기간 값", example = "104")
        private long previous;

        @Schema(description = "증감 (current - previous)", example = "28")
        private long diff;

        @Schema(description = "증감률(%)", example = "26.92")
        private BigDecimal changeRate;
    }

    /**
     * 소수 지표(평균 처리시간 등) 증감.
     * current/previous가 모두 null이면 이 객체 자체가 null일 수 있다.
     */
    @Getter
    @Builder
    @Schema(description = "소수 지표 증감")
    public static class DecimalDelta {
        @Schema(description = "현재 기간 값", example = "12.50", nullable = true)
        private BigDecimal current;

        @Schema(description = "이전 동기간 값", example = "15.00", nullable = true)
        private BigDecimal previous;

        @Schema(description = "증감 (current - previous)", example = "-2.50", nullable = true)
        private BigDecimal diff;

        @Schema(description = "증감률(%)", example = "-16.67", nullable = true)
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
