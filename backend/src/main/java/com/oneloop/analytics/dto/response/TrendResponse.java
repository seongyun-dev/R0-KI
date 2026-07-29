package com.oneloop.analytics.dto.response;

import com.oneloop.analytics.dto.request.AnalyticsBucket;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Getter;

/**
 * trend API 응답 본문(data).
 *
 * <p>프론트 차트 매핑 가이드:
 * - bucket → X축 단위 (day/week/month/hour3)
 * - series[].bucketStart → X축 각 점의 시작 시각
 * - series[].totalCount → Y축 전체 건수
 * - series[].byType / byStatus → 쌓인 막대/필터용 상세 건수
 *
 * <p>day/week/month: 조회 기간 안 빈 구간도 series에 포함 (차트 끊김 방지).
 * hour3: 하루 8칸(0-3 … 21-24) 고정. 기간 내 같은 시각대 이벤트를 날짜 무시하고 합산.
 *        프론트 "시간대별 유형" 차트용. byType으로 주차/쓰레기 그룹핑은 FE 또는 AnalyticsEventGroup 규칙.
 */
@Getter
@Builder
@Schema(description = "기간별 이벤트 발생 추이 응답")
public class TrendResponse {

    @Schema(description = "집계 단위", example = "day")
    private AnalyticsBucket bucket;

    @Schema(description = "시간 구간별 집계 목록 (시간순). hour3는 슬롯 0~7 고정 8개")
    private List<TrendBucketItem> series;

    @Getter
    @Builder
    @Schema(description = "한 개 버킷(일/주/월/3시간)의 집계 결과")
    public static class TrendBucketItem {

        @Schema(description = "버킷 시작 시각", example = "2026-07-01T00:00:00")
        private LocalDateTime bucketStart;

        @Schema(description = "버킷 종료 시각", example = "2026-07-01T23:59:59")
        private LocalDateTime bucketEnd;

        @Schema(description = "해당 버킷 전체 이벤트 수", example = "5")
        private long totalCount;

        @Schema(description = "유형별 건수 (없는 유형은 키 자체가 없을 수 있음)")
        private Map<EventType, Long> byType;

        @Schema(description = "처리 상태별 건수")
        private Map<ProcessingStatus, Long> byStatus;
    }
}
