package com.oneloop.analytics.service;

import com.oneloop.analytics.dto.request.ZoneSort;
import com.oneloop.analytics.dto.response.ByZoneResponse;
import com.oneloop.analytics.dto.response.HandlingResponse;
import com.oneloop.analytics.dto.response.OverviewResponse;
import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.util.CheckpointLocator;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * LLM 인사이트 전용 표 빌더.
 *
 * <p>화면 Analytics API 응답을 통짜 JSON으로 넘기지 않고,
 * 경비원/운영 인사이트에 필요한 4개 표만 마크다운으로 만든다.
 *
 * <ol>
 *   <li>월간(또는 주간) 핵심 요약
 *   <li>이벤트 유형별 현황
 *   <li>구역별 관리 우선순위
 *   <li>미처리·지연 처리
 * </ol>
 *
 * <p>숫자 정의(미처리=DETECTED+PROCESSING, 순찰=COMPLETED 등)는
 * {@link AnalyticsQueryService}와 동일하게 유지한다.
 */
@Component
@RequiredArgsConstructor
public class AnalyticsInsightTableBuilder {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");
    private static final int TOP_ZONE_LIMIT = 5;
    private static final int TOP_PENDING_LIMIT = 5;
    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd");

    private final AnalyticsQueryService analyticsQueryService;
    private final CheckpointLocator checkpointLocator;

    public String buildTablesMarkdown(
            Long apartmentComplexId,
            String periodType,
            String periodKey,
            LocalDateTime periodFrom,
            LocalDateTime periodTo) {

        LocalDateTime[] previous = analyticsQueryService.resolvePreviousPeriod(periodFrom, periodTo);
        LocalDateTime previousFrom = previous[0];
        LocalDateTime previousTo = previous[1];

        OverviewResponse overview =
                analyticsQueryService.getOverview(
                        apartmentComplexId, periodFrom, periodTo, true, null, null, null);
        HandlingResponse currentHandling =
                analyticsQueryService.getHandling(
                        apartmentComplexId, periodFrom, periodTo, null, null);
        HandlingResponse previousHandling =
                analyticsQueryService.getHandling(
                        apartmentComplexId, previousFrom, previousTo, null, null);
        ByZoneResponse byZone =
                analyticsQueryService.getByZone(
                        apartmentComplexId,
                        periodFrom,
                        periodTo,
                        null,
                        null,
                        null,
                        ZoneSort.count_desc);

        List<DetectedEvent> currentEvents =
                analyticsQueryService.findEventsForInsight(
                        apartmentComplexId, periodFrom, periodTo);
        List<DetectedEvent> previousEvents =
                analyticsQueryService.findEventsForInsight(
                        apartmentComplexId, previousFrom, previousTo);
        List<Checkpoint> checkpoints =
                analyticsQueryService.findCheckpointsForInsight(apartmentComplexId);

        StringBuilder sb = new StringBuilder();
        appendMeta(sb, periodType, periodKey, periodFrom, periodTo, previousFrom, previousTo, checkpoints.size());
        sb.append('\n');
        appendSummaryTable(sb, overview, currentHandling, previousHandling);
        sb.append('\n');
        appendTypeTable(sb, currentEvents, previousEvents);
        sb.append('\n');
        appendZoneTable(sb, byZone, currentEvents, checkpoints);
        sb.append('\n');
        appendPendingTable(sb, currentEvents, checkpoints);
        return sb.toString();
    }

    private void appendMeta(
            StringBuilder sb,
            String periodType,
            String periodKey,
            LocalDateTime from,
            LocalDateTime to,
            LocalDateTime previousFrom,
            LocalDateTime previousTo,
            int zoneCount) {
        sb.append("## 분석 기준\n");
        sb.append("- 기간 유형: ").append(periodType).append(" (").append(periodKey).append(")\n");
        sb.append("- 분석 기간: ").append(from).append(" ~ ").append(to).append('\n');
        sb.append("- 비교 기간: ").append(previousFrom).append(" ~ ").append(previousTo).append('\n');
        sb.append("- 기준 시간대: Asia/Seoul\n");
        sb.append("- 순찰 기준: 완료(COMPLETED) 순찰만 집계\n");
        sb.append("- 미처리 기준: 감지됨+처리중 (완료 제외)\n");
        sb.append("- 등록 구역 수: ").append(zoneCount).append('\n');
    }

    private void appendSummaryTable(
            StringBuilder sb,
            OverviewResponse overview,
            HandlingResponse currentHandling,
            HandlingResponse previousHandling) {
        long patrolCurrent = overview.getTotals().getPatrolCount();
        long patrolPrevious =
                overview.getDelta() != null && overview.getDelta().getPatrol() != null
                        ? overview.getDelta().getPatrol().getPrevious()
                        : 0L;
        long eventCurrent = overview.getTotals().getTotalCount();
        long eventPrevious =
                overview.getDelta() != null && overview.getDelta().getTotal() != null
                        ? overview.getDelta().getTotal().getPrevious()
                        : 0L;

        HandlingResponse.HandlingItem curAll = findHandling(currentHandling, "전체");
        HandlingResponse.HandlingItem prevAll = findHandling(previousHandling, "전체");
        long handledCurrent = curAll == null ? 0L : curAll.getHandled();
        long handledPrevious = prevAll == null ? 0L : prevAll.getHandled();
        long pendingCurrent = curAll == null ? 0L : curAll.getPending();
        long pendingPrevious = prevAll == null ? 0L : prevAll.getPending();

        BigDecimal avgCurrent = overview.getTotals().getAvgHandleMin();
        BigDecimal avgPrevious =
                overview.getDelta() != null && overview.getDelta().getHandleTime() != null
                        ? overview.getDelta().getHandleTime().getPrevious()
                        : null;

        BigDecimal rateCurrent = perPatrol(eventCurrent, patrolCurrent);
        BigDecimal ratePrevious = perPatrol(eventPrevious, patrolPrevious);

        sb.append("## 1. 핵심 요약\n");
        sb.append("| 지표 | 이번 기간 | 이전 기간 | 증감 | 증감률 |\n");
        sb.append("|---|---:|---:|---:|---:|\n");
        rowLong(sb, "순찰 횟수", patrolCurrent, patrolPrevious);
        rowLong(sb, "전체 이벤트", eventCurrent, eventPrevious);
        rowLong(sb, "처리 완료", handledCurrent, handledPrevious);
        rowLong(sb, "미처리", pendingCurrent, pendingPrevious);
        rowDecimal(sb, "평균 처리시간(분)", avgCurrent, avgPrevious);
        rowDecimal(sb, "순찰당 이벤트", rateCurrent, ratePrevious);
    }

    private void appendTypeTable(
            StringBuilder sb,
            List<DetectedEvent> currentEvents,
            List<DetectedEvent> previousEvents) {
        Map<EventType, Long> currentCounts = countByType(currentEvents);
        Map<EventType, Long> previousCounts = countByType(previousEvents);
        Map<EventType, Long> pendingByType = countPendingByType(currentEvents);
        Map<EventType, BigDecimal> avgByType = avgHandleByType(currentEvents);
        long totalCurrent = Math.max(1L, currentEvents.size());

        // overview.delta.byType 이 있으면 증감 정렬에 활용, 없으면 현재 건수 기준
        List<EventType> types = new ArrayList<>();
        for (EventType type : EventType.values()) {
            long cur = currentCounts.getOrDefault(type, 0L);
            long prev = previousCounts.getOrDefault(type, 0L);
            if (cur > 0 || prev > 0) {
                types.add(type);
            }
        }
        types.sort(
                Comparator.comparingLong((EventType t) -> currentCounts.getOrDefault(t, 0L))
                        .reversed());

        sb.append("## 2. 이벤트 유형별 현황\n");
        sb.append("| 이벤트 유형 | 이번 기간 | 이전 기간 | 증감 | 비중 | 미처리 | 평균 처리시간(분) |\n");
        sb.append("|---|---:|---:|---:|---:|---:|---:|\n");
        if (types.isEmpty()) {
            sb.append("| (없음) | 0 | 0 | 0 | 0% | 0 | - |\n");
            return;
        }
        for (EventType type : types) {
            long cur = currentCounts.getOrDefault(type, 0L);
            long prev = previousCounts.getOrDefault(type, 0L);
            long diff = cur - prev;
            BigDecimal share =
                    BigDecimal.valueOf(cur * 100.0 / totalCurrent)
                            .setScale(1, RoundingMode.HALF_UP);
            long pending = pendingByType.getOrDefault(type, 0L);
            String avg =
                    avgByType.get(type) == null ? "-" : avgByType.get(type).toPlainString();
            sb.append("| ")
                    .append(AnalyticsInsightEventLabels.toKorean(type))
                    .append(" | ")
                    .append(cur)
                    .append(" | ")
                    .append(prev)
                    .append(" | ")
                    .append(signed(diff))
                    .append(" | ")
                    .append(share)
                    .append("% | ")
                    .append(pending)
                    .append(" | ")
                    .append(avg)
                    .append(" |\n");
        }
    }

    private void appendZoneTable(
            StringBuilder sb,
            ByZoneResponse byZone,
            List<DetectedEvent> currentEvents,
            List<Checkpoint> checkpoints) {
        Map<Long, Long> pendingByZone = countPendingByZone(currentEvents, checkpoints);

        sb.append("## 3. 구역별 관리 우선순위\n");
        sb.append("| 순위 | 구역명 | 이벤트 수 | 순찰 방문 | 순찰당 이벤트 | 주요 유형 | 미처리 |\n");
        sb.append("|---:|---|---:|---:|---:|---|---:|\n");

        List<ByZoneResponse.ByZoneItem> items =
                byZone.getItems() == null ? List.of() : byZone.getItems();
        if (items.isEmpty()) {
            sb.append("| - | (없음) | 0 | 0 | - | - | 0 |\n");
            return;
        }

        int rank = 1;
        for (ByZoneResponse.ByZoneItem item : items.stream().limit(TOP_ZONE_LIMIT).toList()) {
            String rate =
                    item.getEventRatePerPatrol() == null
                            ? "-"
                            : item.getEventRatePerPatrol().toPlainString();
            String topType = AnalyticsInsightEventLabels.toKorean(item.getTopEventType());
            long pending = pendingByZone.getOrDefault(item.getZoneId(), 0L);
            sb.append("| ")
                    .append(rank++)
                    .append(" | ")
                    .append(nullToDash(item.getZoneName()))
                    .append(" | ")
                    .append(item.getEventCount())
                    .append(" | ")
                    .append(item.getPatrolCount())
                    .append(" | ")
                    .append(rate)
                    .append(" | ")
                    .append(topType)
                    .append(" | ")
                    .append(pending)
                    .append(" |\n");
        }
    }

    private void appendPendingTable(
            StringBuilder sb, List<DetectedEvent> currentEvents, List<Checkpoint> checkpoints) {
        LocalDateTime now = LocalDateTime.now(SERVICE_ZONE);
        Map<String, PendingAgg> aggs = new HashMap<>();

        for (DetectedEvent event : currentEvents) {
            if (event.getProcessingStatus() == ProcessingStatus.COMPLETED) {
                continue;
            }
            String zoneName =
                    checkpointLocator
                            .findContaining(checkpoints, event.getX(), event.getY())
                            .map(Checkpoint::getName)
                            .orElse("구역 미상");
            String typeName = AnalyticsInsightEventLabels.toKorean(event.getType());
            String key = zoneName + "|" + typeName;
            PendingAgg agg = aggs.computeIfAbsent(key, ignored -> new PendingAgg(zoneName, typeName));
            agg.count++;
            if (event.getOccurredAt() != null) {
                if (agg.firstOccurred == null || event.getOccurredAt().isBefore(agg.firstOccurred)) {
                    agg.firstOccurred = event.getOccurredAt();
                }
                long waitMinutes = Duration.between(event.getOccurredAt(), now).toMinutes();
                if (waitMinutes > agg.maxWaitMinutes) {
                    agg.maxWaitMinutes = waitMinutes;
                }
            }
        }

        List<PendingAgg> ranked =
                aggs.values().stream()
                        .sorted(
                                Comparator.comparingLong((PendingAgg a) -> a.maxWaitMinutes)
                                        .reversed()
                                        .thenComparingLong(a -> a.count)
                                        .reversed())
                        .limit(TOP_PENDING_LIMIT)
                        .toList();

        sb.append("## 4. 미처리·지연 처리\n");
        sb.append("| 우선순위 | 구역 | 유형 | 미처리 건수 | 최장 대기 | 최초 발생일 |\n");
        sb.append("|---:|---|---|---:|---|---|\n");
        if (ranked.isEmpty()) {
            sb.append("| - | (없음) | - | 0 | - | - |\n");
            return;
        }
        int rank = 1;
        for (PendingAgg agg : ranked) {
            sb.append("| ")
                    .append(rank++)
                    .append(" | ")
                    .append(agg.zoneName)
                    .append(" | ")
                    .append(agg.typeName)
                    .append(" | ")
                    .append(agg.count)
                    .append(" | ")
                    .append(formatWait(agg.maxWaitMinutes))
                    .append(" | ")
                    .append(
                            agg.firstOccurred == null
                                    ? "-"
                                    : agg.firstOccurred.toLocalDate().format(DATE_FMT))
                    .append(" |\n");
        }
    }

    private HandlingResponse.HandlingItem findHandling(HandlingResponse response, String label) {
        if (response == null || response.getItems() == null) {
            return null;
        }
        return response.getItems().stream()
                .filter(item -> label.equals(item.getLabel()))
                .findFirst()
                .orElse(null);
    }

    private Map<EventType, Long> countByType(List<DetectedEvent> events) {
        Map<EventType, Long> map = new EnumMap<>(EventType.class);
        for (DetectedEvent event : events) {
            if (event.getType() != null) {
                map.merge(event.getType(), 1L, Long::sum);
            }
        }
        return map;
    }

    private Map<EventType, Long> countPendingByType(List<DetectedEvent> events) {
        Map<EventType, Long> map = new EnumMap<>(EventType.class);
        for (DetectedEvent event : events) {
            if (event.getType() == null) {
                continue;
            }
            if (event.getProcessingStatus() != ProcessingStatus.COMPLETED) {
                map.merge(event.getType(), 1L, Long::sum);
            }
        }
        return map;
    }

    private Map<EventType, BigDecimal> avgHandleByType(List<DetectedEvent> events) {
        Map<EventType, long[]> acc = new EnumMap<>(EventType.class);
        for (DetectedEvent event : events) {
            if (event.getType() == null
                    || event.getProcessingStatus() != ProcessingStatus.COMPLETED
                    || event.getProcessedAt() == null
                    || event.getOccurredAt() == null) {
                continue;
            }
            long minutes = Duration.between(event.getOccurredAt(), event.getProcessedAt()).toMinutes();
            if (minutes < 0) {
                continue;
            }
            long[] pair = acc.computeIfAbsent(event.getType(), ignored -> new long[2]);
            pair[0] += minutes;
            pair[1] += 1;
        }
        Map<EventType, BigDecimal> result = new EnumMap<>(EventType.class);
        for (Map.Entry<EventType, long[]> entry : acc.entrySet()) {
            long[] pair = entry.getValue();
            if (pair[1] == 0) {
                continue;
            }
            result.put(
                    entry.getKey(),
                    BigDecimal.valueOf(pair[0])
                            .divide(BigDecimal.valueOf(pair[1]), 1, RoundingMode.HALF_UP));
        }
        return result;
    }

    private Map<Long, Long> countPendingByZone(
            List<DetectedEvent> events, List<Checkpoint> checkpoints) {
        Map<Long, Long> map = new HashMap<>();
        for (DetectedEvent event : events) {
            if (event.getProcessingStatus() == ProcessingStatus.COMPLETED) {
                continue;
            }
            checkpointLocator
                    .findContaining(checkpoints, event.getX(), event.getY())
                    .ifPresent(checkpoint -> map.merge(checkpoint.getId(), 1L, Long::sum));
        }
        return map;
    }

    private BigDecimal perPatrol(long events, long patrols) {
        if (patrols <= 0L) {
            return null;
        }
        return BigDecimal.valueOf(events)
                .divide(BigDecimal.valueOf(patrols), 2, RoundingMode.HALF_UP);
    }

    private void rowLong(StringBuilder sb, String label, long current, long previous) {
        long diff = current - previous;
        sb.append("| ")
                .append(label)
                .append(" | ")
                .append(current)
                .append(" | ")
                .append(previous)
                .append(" | ")
                .append(signed(diff))
                .append(" | ")
                .append(rateText(diff, previous))
                .append(" |\n");
    }

    private void rowDecimal(
            StringBuilder sb, String label, BigDecimal current, BigDecimal previous) {
        String curText = current == null ? "-" : current.toPlainString();
        String prevText = previous == null ? "-" : previous.toPlainString();
        String diffText = "-";
        String rate = "-";
        if (current != null && previous != null) {
            BigDecimal diff = current.subtract(previous);
            diffText = signedDecimal(diff);
            rate = rateTextDecimal(diff, previous);
        }
        sb.append("| ")
                .append(label)
                .append(" | ")
                .append(curText)
                .append(" | ")
                .append(prevText)
                .append(" | ")
                .append(diffText)
                .append(" | ")
                .append(rate)
                .append(" |\n");
    }

    private String signed(long value) {
        return value > 0 ? "+" + value : Long.toString(value);
    }

    private String signedDecimal(BigDecimal value) {
        if (value.signum() > 0) {
            return "+" + value.toPlainString();
        }
        return value.toPlainString();
    }

    private String rateText(long diff, long previous) {
        if (previous == 0L) {
            return diff == 0L ? "0%" : "-";
        }
        BigDecimal rate =
                BigDecimal.valueOf(diff * 100.0 / previous).setScale(1, RoundingMode.HALF_UP);
        return signedDecimal(rate) + "%";
    }

    private String rateTextDecimal(BigDecimal diff, BigDecimal previous) {
        if (previous == null || previous.compareTo(BigDecimal.ZERO) == 0) {
            return "-";
        }
        BigDecimal rate =
                diff.multiply(BigDecimal.valueOf(100))
                        .divide(previous, 1, RoundingMode.HALF_UP);
        return signedDecimal(rate) + "%";
    }

    private String formatWait(long minutes) {
        if (minutes <= 0) {
            return "-";
        }
        long days = minutes / (60 * 24);
        long hours = (minutes % (60 * 24)) / 60;
        if (days > 0) {
            return days + "일 " + hours + "시간";
        }
        if (hours > 0) {
            return hours + "시간";
        }
        return minutes + "분";
    }

    private String nullToDash(String value) {
        return value == null || value.isBlank() ? "-" : value;
    }

    private static final class PendingAgg {
        private final String zoneName;
        private final String typeName;
        private long count;
        private long maxWaitMinutes;
        private LocalDateTime firstOccurred;

        private PendingAgg(String zoneName, String typeName) {
            this.zoneName = Objects.requireNonNull(zoneName);
            this.typeName = Objects.requireNonNull(typeName);
        }
    }
}
