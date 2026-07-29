package com.oneloop.analytics.dto.response;

import com.oneloop.event.domain.EventType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

/**
 * by-zone API 응답 본문(data).
 *
 * <p>프론트 차트 매핑 가이드:
 * - items[].zoneName / eventCount → 구역별 막대 차트
 * - items[].eventRatePerPatrol → 순찰 대비 위험도 (선택 표시)
 * - topZone → "가장 문제인 구역" 카드
 *
 * <p>순찰 대비 필드(patrolCount, eventRatePerPatrol)는 명세 대응용이다.
 * 프론트에서 안 쓰면 응답 필드를 나중에 제거해도 된다.
 */
@Getter
@Builder
@Schema(description = "구역별 이벤트 통계 응답")
public class ByZoneResponse {

    @Schema(description = "구역별 집계 목록")
    private List<ByZoneItem> items;

    @Schema(description = "이벤트가 가장 많이 발생한 구역", nullable = true)
    private TopZone topZone;

    @Getter
    @Builder
    @Schema(description = "구역 1개의 통계")
    public static class ByZoneItem {

        @Schema(description = "구역 ID", example = "12")
        private Long zoneId;

        @Schema(description = "구역 이름", example = "지상 주차장 A")
        private String zoneName;

        @Schema(description = "해당 구역 이벤트 발생 건수", example = "46")
        private long eventCount;

        @Schema(description = "해당 구역 순찰 방문 횟수 (patrol_checkpoint_visits 기준)", example = "21")
        private long patrolCount;

        @Schema(
                description = "순찰 1회당 평균 이벤트 수 (eventCount/patrolCount). 방문 0회면 null",
                example = "2.19",
                nullable = true)
        private BigDecimal eventRatePerPatrol;

        @Schema(description = "해당 구역에서 가장 많이 발생한 이벤트 유형", example = "ILLEGAL_PARKING", nullable = true)
        private EventType topEventType;
    }

    @Getter
    @Builder
    @Schema(description = "최다 발생 구역 요약")
    public static class TopZone {

        @Schema(description = "구역 ID", example = "12")
        private Long zoneId;

        @Schema(description = "구역 이름", example = "지상 주차장 A")
        private String zoneName;

        @Schema(description = "이벤트 건수", example = "46")
        private long eventCount;
    }
}
