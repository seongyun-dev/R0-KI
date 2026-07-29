package com.oneloop.analytics.service;

import com.oneloop.analytics.dto.request.AnalyticsBucket;
import com.oneloop.analytics.dto.request.ZoneSort;
import com.oneloop.analytics.dto.response.ByTypeResponse;
import com.oneloop.analytics.dto.response.ByZoneResponse;
import com.oneloop.analytics.dto.response.OverviewResponse;
import com.oneloop.analytics.dto.response.TrendResponse;
import com.oneloop.analytics.repository.AnalyticsRepository;
import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 이벤트 분석(대시보드 통계) 조회 서비스.
 *
 * <p>역할: DB에 저장된 DetectedEvent를 기간/유형/로봇/구역 조건으로 모아,
 * 프론트 그래프·요약 카드에 바로 쓸 수 있는 숫자로 계산한다.
 *
 * <p>일반 이벤트 목록 API(EventService)와 다른 점:
 * - EventService: 개별 이벤트 행을 보여줌
 * - AnalyticsQueryService: 여러 이벤트를 합쳐 건수/비율/증감/최다 항목을 계산
 *
 * <p>읽기 전용(readOnly=true)이다. 통계 API는 DB를 수정하지 않는다.
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AnalyticsQueryService {

    // "오늘" 같은 날짜 경계를 서버 OS 타임존이 아니라 KST로 고정한다.
    // 서버가 UTC로 떠도 관리자 화면의 "오늘"이 한국 기준과 어긋나지 않게 하기 위함.
    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");

    private final AnalyticsRepository analyticsRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final CheckpointLocator checkpointLocator;
    private final PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;

    /**
     * [이벤트 전체 현황 요약]
     * 대시보드 상단 카드에 필요한 핵심 숫자를 한 번에 계산한다.
     *
     * <p>프론트가 이 API로 얻는 것:
     * - 조회 기간 전체 이벤트 수
     * - 오늘 발생한 이벤트 수
     * - 가장 많이 난 이벤트 유형
     * - 가장 많이 난 구역
     * - 이전 같은 길이의 기간 대비 증감(전체/유형별)
     *
     * <p>왜 따로 overview API가 필요한가:
     * trend(시계열)만으로는 "최다 구역", "이전 대비 증감"을 프론트마다 다르게 계산할 위험이 있다.
     * 서버에서 기준을 고정해 카드 숫자가 항상 같게 나오게 한다.
     *
     * @param apartmentComplexId 로그인 관리자 소속 단지 ID (타 단지 데이터 조회 방지)
     * @param from 조회 시작 시각 (포함)
     * @param to 조회 종료 시각 (포함)
     * @param compare true면 이전 동기간 대비 증감 계산
     * @param zoneIds 구역 필터. null/빈 목록이면 전체 구역
     * @param eventTypes 유형 필터. null/빈 목록이면 전체 유형
     * @param robotIds 로봇 필터. null/빈 목록이면 전체 로봇
     * @return 요약 카드용 OverviewResponse
     */
    public OverviewResponse getOverview(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            boolean compare,
            List<Long> zoneIds,
            List<EventType> eventTypes,
            List<Long> robotIds) {
        // from이 to보다 이후면 집계 의미가 없으므로 바로 400 처리
        validateRange(from, to);

        // 구역 통계/필터는 이벤트에 zoneId가 직접 없어서, 좌표(x,y) → Checkpoint 매핑이 필요하다.
        // 단지 지도의 체크포인트(구역)를 한 번만 가져와 아래에서 재사용한다.
        List<Checkpoint> checkpoints = findCheckpoints(apartmentComplexId);

        // 1) 현재 조회 기간 이벤트
        //    DB에서 기간·유형·로봇으로 먼저 걸러온 뒤, zoneIds가 있으면 좌표 기준으로 추가 필터
        List<DetectedEvent> currentEvents =
                filterByZone(
                        findEvents(apartmentComplexId, from, to, eventTypes, robotIds),
                        checkpoints,
                        zoneIds);

        // 2) "오늘" 카드용 이벤트
        //    요청 기간과 별개로, KST 기준 오늘 00:00 ~ 내일 00:00 구간을 따로 센다.
        DateRange today = todayRange();
        List<DetectedEvent> todayEvents =
                filterByZone(
                        findEvents(
                                apartmentComplexId,
                                today.from(),
                                today.to(),
                                eventTypes,
                                robotIds),
                        checkpoints,
                        zoneIds);

        // 3) 최다 유형 / 최다 구역
        //    이벤트가 0건이면 topType, topZone 모두 null이 된다. (데이터 없는 초기 환경 정상)
        Map<EventType, Long> currentTypeCounts = countByType(currentEvents);
        OverviewResponse.Zone topZone = findTopZone(currentEvents, checkpoints);
        EventType topType =
                currentTypeCounts.entrySet().stream()
                        .max(Map.Entry.comparingByValue())
                        .map(Map.Entry::getKey)
                        .orElse(null);

        // 4) 이전 동기간 대비 증감
        //    compare=false면 previous를 0으로 두고 diff/changeRate만 계산한다.
        OverviewResponse.TotalDelta totalDelta;
        List<OverviewResponse.TypeDelta> typeDeltas = new ArrayList<>();
        if (compare) {
            // 예: 7/1~7/31(31일) 조회면 이전 구간은 바로 앞 31일
            DateRange previous = previousRange(from, to);
            List<DetectedEvent> previousEvents =
                    filterByZone(
                            findEvents(
                                    apartmentComplexId,
                                    previous.from(),
                                    previous.to(),
                                    eventTypes,
                                    robotIds),
                            checkpoints,
                            zoneIds);
            Map<EventType, Long> previousTypeCounts = countByType(previousEvents);
            totalDelta = buildTotalDelta(currentEvents.size(), previousEvents.size());
            typeDeltas = buildTypeDeltas(currentTypeCounts, previousTypeCounts);
        } else {
            totalDelta = buildTotalDelta(currentEvents.size(), 0);
        }

        // 5) 프론트 명세 형태의 응답 DTO로 조립
        return OverviewResponse.builder()
                .period(
                        OverviewResponse.Period.builder()
                                .from(from)
                                .to(to)
                                .timezone(SERVICE_ZONE.getId())
                                .build())
                .totals(
                        OverviewResponse.Totals.builder()
                                .totalCount(currentEvents.size())
                                .todayCount(todayEvents.size())
                                .build())
                .top(OverviewResponse.Top.builder().eventType(topType).zone(topZone).build())
                .delta(OverviewResponse.Delta.builder().total(totalDelta).byType(typeDeltas).build())
                .build();
    }

    /**
     * [기간별 이벤트 발생 추이]
     * 일/주/월 단위로 이벤트 건수를 나눠, 차트(선/막대)용 시계열 데이터를 만든다.
     *
     * <p>프론트가 이 API로 얻는 것:
     * - X축: bucketStart (하루/한 주/한 달의 시작점)
     * - Y축: totalCount
     * - 상세: byType, byStatus (필터·쌓인 차트용)
     *
     * <p>overview와 다른 점:
     * - overview: 기간 전체를 한 덩어리로 요약
     * - trend: 같은 기간을 bucket 단위로 쪼개 시간 순 배열로 반환
     *
     * <p>빈 구간도 series에 포함한다.
     * 예: 7일에 이벤트 0건이어도 day 버킷 하나는 나와야 차트가 끊기지 않는다.
     *
     * @param apartmentComplexId 로그인 관리자 소속 단지 ID
     * @param from 조회 시작 시각
     * @param to 조회 종료 시각
     * @param bucket 집계 단위 (day/week/month)
     * @param zoneIds 구역 필터 (없으면 전체)
     * @param eventTypes 유형 필터 (없으면 전체)
     * @param robotIds 로봇 필터 (없으면 전체)
     * @param statuses 처리상태 필터 (없으면 전체)
     * @return TrendResponse 시계열 집계 결과
     */
    public TrendResponse getTrend(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            AnalyticsBucket bucket,
            List<Long> zoneIds,
            List<EventType> eventTypes,
            List<Long> robotIds,
            List<ProcessingStatus> statuses) {
        validateRange(from, to);
        if (bucket == null) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }

        List<Checkpoint> checkpoints = findCheckpoints(apartmentComplexId);

        // 1) 조건에 맞는 원본 이벤트 조회 후 구역 필터
        List<DetectedEvent> events =
                filterByZone(
                        findEvents(
                                apartmentComplexId,
                                from,
                                to,
                                eventTypes,
                                robotIds,
                                statuses),
                        checkpoints,
                        zoneIds);

        // 2) 이벤트들을 버킷 시작 시각 기준으로 묶는다.
        //    LinkedHashMap이 아니라 일단 HashMap에 넣고, series 생성 때 시간순으로 맞춘다.
        Map<LocalDateTime, List<DetectedEvent>> eventsByBucket = new HashMap<>();
        for (DetectedEvent event : events) {
            LocalDateTime bucketStart = resolveBucketStart(event.getOccurredAt(), bucket);
            eventsByBucket.computeIfAbsent(bucketStart, key -> new ArrayList<>()).add(event);
        }

        // 3) from~to 사이의 모든 버킷을 순서대로 만들고, 이벤트 없는 구간은 0건으로 채운다.
        List<TrendResponse.TrendBucketItem> series = new ArrayList<>();
        LocalDateTime cursor = resolveBucketStart(from, bucket);
        // to가 어떤 버킷에 속하는지도 포함해야 하므로, to의 버킷 시작까지 반복
        LocalDateTime lastBucketStart = resolveBucketStart(to, bucket);
        while (!cursor.isAfter(lastBucketStart)) {
            List<DetectedEvent> bucketEvents = eventsByBucket.getOrDefault(cursor, List.of());
            series.add(
                    TrendResponse.TrendBucketItem.builder()
                            .bucketStart(cursor)
                            .bucketEnd(resolveBucketEnd(cursor, bucket))
                            .totalCount(bucketEvents.size())
                            .byType(countByType(bucketEvents))
                            .byStatus(countByStatus(bucketEvents))
                            .build());
            cursor = nextBucketStart(cursor, bucket);
        }

        return TrendResponse.builder().bucket(bucket).series(series).build();
    }

    /**
     * [이벤트 유형별 통계]
     * 조회 기간 동안 유형별 건수·비율·이전 동기간 대비 증감을 계산한다.
     *
     * <p>프론트가 이 API로 얻는 것:
     * - 유형별 막대/파이 차트 데이터
     * - 각 유형이 전체에서 차지하는 비율
     * - 이전 같은 길이의 기간보다 늘었는지/줄었는지
     *
     * <p>overview / trend와 다른 점:
     * - overview: 최다 유형 1개 + 요약 숫자
     * - trend: 시간축으로 쪼갠 건수
     * - by-type: 유형 축으로 전체를 나눠 보여줌
     *
     * <p>정렬: 건수 많은 유형이 위로 오도록 내림차순.
     * 차트가 "큰 문제부터" 보이게 하기 위함이다.
     *
     * @param apartmentComplexId 로그인 관리자 소속 단지 ID
     * @param from 조회 시작 시각
     * @param to 조회 종료 시각
     * @param compare true면 이전 동기간 대비 증감 계산
     * @param zoneIds 구역 필터 (없으면 전체)
     * @param robotIds 로봇 필터 (없으면 전체)
     * @param statuses 처리상태 필터 (없으면 전체)
     * @return ByTypeResponse 유형별 통계
     */
    public ByTypeResponse getByType(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            boolean compare,
            List<Long> zoneIds,
            List<Long> robotIds,
            List<ProcessingStatus> statuses) {
        validateRange(from, to);
        List<Checkpoint> checkpoints = findCheckpoints(apartmentComplexId);

        // 1) 현재 기간 이벤트 (유형 필터는 넣지 않음 — 유형별 전체를 보는 API이기 때문)
        List<DetectedEvent> currentEvents =
                filterByZone(
                        findEvents(
                                apartmentComplexId, from, to, null, robotIds, statuses),
                        checkpoints,
                        zoneIds);
        Map<EventType, Long> currentTypeCounts = countByType(currentEvents);
        long totalCount = currentEvents.size();

        // 2) 이전 동기간 유형별 건수 (compare=false면 빈 Map → previous=0으로 계산)
        Map<EventType, Long> previousTypeCounts = Map.of();
        if (compare) {
            DateRange previous = previousRange(from, to);
            List<DetectedEvent> previousEvents =
                    filterByZone(
                            findEvents(
                                    apartmentComplexId,
                                    previous.from(),
                                    previous.to(),
                                    null,
                                    robotIds,
                                    statuses),
                            checkpoints,
                            zoneIds);
            previousTypeCounts = countByType(previousEvents);
        }

        // 3) 현재 기간에 한 번이라도 나온 유형만 항목으로 만든다.
        //    데이터 없는 초기에는 items=[] 가 된다.
        Map<EventType, Long> finalPreviousTypeCounts = previousTypeCounts;
        List<ByTypeResponse.ByTypeItem> items =
                currentTypeCounts.entrySet().stream()
                        .sorted(Map.Entry.<EventType, Long>comparingByValue().reversed())
                        .map(
                                entry -> {
                                    EventType type = entry.getKey();
                                    long current = entry.getValue();
                                    long previous = finalPreviousTypeCounts.getOrDefault(type, 0L);
                                    long diff = current - previous;
                                    return ByTypeResponse.ByTypeItem.builder()
                                            .eventType(type)
                                            .count(current)
                                            .ratio(calculateRatio(current, totalCount))
                                            .delta(
                                                    ByTypeResponse.Delta.builder()
                                                            .current(current)
                                                            .previous(previous)
                                                            .diff(diff)
                                                            .changeRate(
                                                                    calculateChangeRate(
                                                                            previous, diff))
                                                            .build())
                                            .build();
                                })
                        .toList();

        return ByTypeResponse.builder().totalCount(totalCount).items(items).build();
    }

    /**
     * [구역별 이벤트 통계]
     * 좌표→체크포인트 매핑으로 구역별 이벤트 건수를 세고,
     * 같은 기간의 구역 방문 횟수와 순찰 대비 비율을 함께 계산한다.
     *
     * <p>프론트가 이 API로 얻는 것:
     * - 구역별 이벤트 막대 차트
     * - 최다 발생 구역(topZone)
     * - 순찰 대비 비율 (나중에 안 쓰면 필드만 제거 가능)
     *
     * <p>순찰 대비 정의 (현재 확정값):
     * - patrolCount = patrol_checkpoint_visits 방문 횟수 (같은 순찰에서 2번 방문하면 2)
     * - eventRatePerPatrol = eventCount / patrolCount
     * - patrolCount=0 이면 rate=null (0으로 나누지 않음)
     *
     * <p>구역 매핑 정책:
     * CheckpointLocator.findContaining(정확히 사각형 안)만 사용.
     * "근처" 폴백은 통계에 넣지 않는다.
     *
     * @param apartmentComplexId 로그인 관리자 소속 단지 ID
     * @param from 조회 시작 시각
     * @param to 조회 종료 시각
     * @param eventTypes 유형 필터 (없으면 전체)
     * @param robotIds 로봇 필터 (없으면 전체)
     * @param statuses 처리상태 필터 (없으면 전체)
     * @param sort 정렬 (count_desc | rate_desc), null이면 count_desc
     * @return ByZoneResponse 구역별 통계
     */
    public ByZoneResponse getByZone(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            List<EventType> eventTypes,
            List<Long> robotIds,
            List<ProcessingStatus> statuses,
            ZoneSort sort) {
        validateRange(from, to);
        ZoneSort effectiveSort = sort == null ? ZoneSort.count_desc : sort;

        List<Checkpoint> checkpoints = findCheckpoints(apartmentComplexId);
        Map<Long, String> zoneNames = new HashMap<>();
        for (Checkpoint checkpoint : checkpoints) {
            zoneNames.put(checkpoint.getId(), checkpoint.getName());
        }

        // 1) 이벤트 조회 후 좌표→구역 매핑하여 구역별 건수/유형 집계
        List<DetectedEvent> events =
                findEvents(apartmentComplexId, from, to, eventTypes, robotIds, statuses);

        Map<Long, Long> eventCountByZone = new HashMap<>();
        Map<Long, Map<EventType, Long>> typeCountByZone = new HashMap<>();
        for (DetectedEvent event : events) {
            checkpointLocator
                    .findContaining(checkpoints, event.getX(), event.getY())
                    .ifPresent(
                            checkpoint -> {
                                Long zoneId = checkpoint.getId();
                                eventCountByZone.merge(zoneId, 1L, Long::sum);
                                typeCountByZone
                                        .computeIfAbsent(zoneId, key -> new HashMap<>())
                                        .merge(event.getType(), 1L, Long::sum);
                            });
        }

        // 2) 같은 기간·로봇 필터로 구역별 방문 횟수(분모) 조회
        Map<Long, Long> patrolCountByZone = findPatrolCountByZone(apartmentComplexId, from, to, robotIds);

        // 3) 이벤트가 한 건이라도 있는 구역만 응답 항목으로 만든다.
        //    (방문만 있고 이벤트 0인 구역은 이번 차트 범위에서 제외)
        List<ByZoneResponse.ByZoneItem> items =
                eventCountByZone.entrySet().stream()
                        .map(
                                entry -> {
                                    Long zoneId = entry.getKey();
                                    long eventCount = entry.getValue();
                                    long patrolCount = patrolCountByZone.getOrDefault(zoneId, 0L);
                                    return ByZoneResponse.ByZoneItem.builder()
                                            .zoneId(zoneId)
                                            .zoneName(zoneNames.get(zoneId))
                                            .eventCount(eventCount)
                                            .patrolCount(patrolCount)
                                            .eventRatePerPatrol(
                                                    calculateEventRate(eventCount, patrolCount))
                                            .topEventType(findTopType(typeCountByZone.get(zoneId)))
                                            .build();
                                })
                        .sorted(zoneComparator(effectiveSort))
                        .toList();

        ByZoneResponse.TopZone topZone =
                items.stream()
                        .max(Comparator.comparingLong(ByZoneResponse.ByZoneItem::getEventCount))
                        .map(
                                item ->
                                        ByZoneResponse.TopZone.builder()
                                                .zoneId(item.getZoneId())
                                                .zoneName(item.getZoneName())
                                                .eventCount(item.getEventCount())
                                                .build())
                        .orElse(null);

        return ByZoneResponse.builder().items(items).topZone(topZone).build();
    }

    /**
     * 구역별 순찰 방문 횟수 Map을 만든다.
     * robotIds 필터가 있으면 해당 로봇 순찰의 방문만 분모에 포함한다.
     */
    private Map<Long, Long> findPatrolCountByZone(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            List<Long> robotIds) {
        boolean hasRobotIds = robotIds != null && !robotIds.isEmpty();
        List<Object[]> rows =
                patrolCheckpointVisitRepository.countVisitsGroupedByCheckpoint(
                        apartmentComplexId,
                        from,
                        to,
                        hasRobotIds,
                        hasRobotIds ? robotIds : List.of(-1L));

        Map<Long, Long> result = new HashMap<>();
        for (Object[] row : rows) {
            Long zoneId = (Long) row[0];
            Long count = (Long) row[1];
            result.put(zoneId, count);
        }
        return result;
    }

    /**
     * 순찰 대비 이벤트 비율.
     * patrolCount=0 이면 null (0 나눗셈 방지, "아직 방문 기록 없음"을 표현).
     */
    private BigDecimal calculateEventRate(long eventCount, long patrolCount) {
        if (patrolCount == 0L) {
            return null;
        }
        return BigDecimal.valueOf(eventCount)
                .divide(BigDecimal.valueOf(patrolCount), 2, RoundingMode.HALF_UP);
    }

    /** 구역 내 유형별 건수 Map에서 최다 유형 1개를 고른다. */
    private EventType findTopType(Map<EventType, Long> typeCounts) {
        if (typeCounts == null || typeCounts.isEmpty()) {
            return null;
        }
        return typeCounts.entrySet().stream()
                .max(Map.Entry.comparingByValue())
                .map(Map.Entry::getKey)
                .orElse(null);
    }

    /**
     * 구역 목록 정렬 Comparator.
     * rate_desc일 때 rate=null 인 항목은 뒤로 보낸다.
     */
    private Comparator<ByZoneResponse.ByZoneItem> zoneComparator(ZoneSort sort) {
        if (sort == ZoneSort.rate_desc) {
            return Comparator.comparing(
                            ByZoneResponse.ByZoneItem::getEventRatePerPatrol,
                            Comparator.nullsLast(Comparator.reverseOrder()))
                    .thenComparing(ByZoneResponse.ByZoneItem::getEventCount, Comparator.reverseOrder());
        }
        return Comparator.comparingLong(ByZoneResponse.ByZoneItem::getEventCount).reversed();
    }

    /**
     * 전체 대비 비율(%) 계산.
     * total=0이면 0으로 둔다. (0으로 나누기 방지)
     */
    private BigDecimal calculateRatio(long count, long total) {
        if (total == 0L) {
            return BigDecimal.ZERO;
        }
        return BigDecimal.valueOf(count)
                .multiply(BigDecimal.valueOf(100))
                .divide(BigDecimal.valueOf(total), 2, RoundingMode.HALF_UP);
    }

    /**
     * AnalyticsRepository 호출을 감싸는 공통 조회 메서드.
     *
     * <p>왜 필요한가:
     * JPQL에서 "리스트가 비었으면 필터 생략"을 `(:list IS NULL OR x IN :list)`로 쓰면
     * Hibernate가 List를 단일 Enum으로 캐스팅하려다 ClassCastException이 난다.
     * 그래서 필터 존재 여부를 boolean(hasXxx)로 넘기고,
     * 필터가 없을 때는 IN 절에 쓰이지 않는 더미 값만 바인딩한다.
     */
    private List<DetectedEvent> findEvents(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            List<EventType> eventTypes,
            List<Long> robotIds) {
        // overview는 처리상태 필터를 쓰지 않으므로 statuses=null
        return findEvents(apartmentComplexId, from, to, eventTypes, robotIds, null);
    }

    private List<DetectedEvent> findEvents(
            Long apartmentComplexId,
            LocalDateTime from,
            LocalDateTime to,
            List<EventType> eventTypes,
            List<Long> robotIds,
            List<ProcessingStatus> statuses) {
        boolean hasEventTypes = eventTypes != null && !eventTypes.isEmpty();
        boolean hasRobotIds = robotIds != null && !robotIds.isEmpty();
        boolean hasStatuses = statuses != null && !statuses.isEmpty();

        return analyticsRepository.findEventsForAnalytics(
                apartmentComplexId,
                from,
                to,
                hasEventTypes,
                // hasEventTypes=false면 쿼리에서 IN 조건을 타지 않음. 바인딩만 필요해서 더미 사용
                hasEventTypes ? eventTypes : List.of(EventType.EMERGENCY),
                hasRobotIds,
                // 존재하지 않을 로봇 ID. hasRobotIds=false면 IN 조건 미적용
                hasRobotIds ? robotIds : List.of(-1L),
                hasStatuses,
                hasStatuses ? statuses : List.of(ProcessingStatus.DETECTED));
    }

    /**
     * 이벤트가 속한 버킷의 시작 시각을 계산한다.
     * - day: 그날 00:00:00
     * - week: 그 주 월요일 00:00:00 (월~일)
     * - month: 그 달 1일 00:00:00
     */
    private LocalDateTime resolveBucketStart(LocalDateTime dateTime, AnalyticsBucket bucket) {
        LocalDate date = dateTime.toLocalDate();
        return switch (bucket) {
            case day -> date.atStartOfDay();
            case week -> date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)).atStartOfDay();
            case month -> date.withDayOfMonth(1).atStartOfDay();
        };
    }

    /**
     * 버킷의 끝 시각(포함)을 계산한다.
     * 차트 툴팁에 "이 구간의 끝"을 보여주기 쉽게 초 단위 inclusive로 둔다.
     * 예: day 2026-07-01 00:00:00 → end 2026-07-01 23:59:59
     */
    private LocalDateTime resolveBucketEnd(LocalDateTime bucketStart, AnalyticsBucket bucket) {
        return nextBucketStart(bucketStart, bucket).minusSeconds(1);
    }

    /** 다음 버킷 시작 시각으로 이동한다. */
    private LocalDateTime nextBucketStart(LocalDateTime bucketStart, AnalyticsBucket bucket) {
        return switch (bucket) {
            case day -> bucketStart.plusDays(1);
            case week -> bucketStart.plusWeeks(1);
            case month -> bucketStart.plusMonths(1);
        };
    }

    /**
     * 처리 상태별 건수를 Map으로 만든다.
     * EnumMap을 쓰면 상태 enum 순서(DETECTED→PROCESSING→COMPLETED)가 안정적이다.
     */
    private Map<ProcessingStatus, Long> countByStatus(List<DetectedEvent> events) {
        Map<ProcessingStatus, Long> result = new EnumMap<>(ProcessingStatus.class);
        for (DetectedEvent event : events) {
            result.merge(event.getProcessingStatus(), 1L, Long::sum);
        }
        return result;
    }

    /**
     * 조회 기간 유효성 검사.
     * from/to가 없거나 from >= to 이면 INVALID_INPUT(COMMON_001)을 던진다.
     */
    private void validateRange(LocalDateTime from, LocalDateTime to) {
        if (from == null || to == null || !from.isBefore(to)) {
            throw new BusinessException(ErrorCode.INVALID_INPUT);
        }
    }

    /**
     * 단지에 등록된 순찰 지도의 체크포인트(구역) 목록을 가져온다.
     * 지도가 아직 없으면 빈 목록을 반환한다.
     * → 이 경우 구역 필터/최다 구역은 매칭되지 않아 top.zone=null이 될 수 있다.
     */
    private List<Checkpoint> findCheckpoints(Long apartmentComplexId) {
        Optional<PatrolMap> patrolMap = patrolMapRepository.findByApartmentComplexId(apartmentComplexId);
        return patrolMap.map(map -> checkpointRepository.findAllByPatrolMapId(map.getId())).orElseGet(List::of);
    }

    /**
     * 이벤트 좌표가 선택한 구역(체크포인트 사각형) 안에 들어오는 것만 남긴다.
     *
     * <p>왜 서비스에서 필터하나:
     * DetectedEvent 테이블에 zoneId 컬럼이 없고 x/y만 있다.
     * 그래서 DB WHERE로 바로 zoneId를 걸 수 없고, CheckpointLocator로 좌표 포함 여부를 본다.
     *
     * <p>주의: findContaining(정확히 사각형 안)만 사용한다.
     * 목록 API의 "근처" 폴백 이름은 통계 집계에는 쓰지 않는다. (모호한 위치까지 구역으로 세지 않기 위함)
     */
    private List<DetectedEvent> filterByZone(
            List<DetectedEvent> events, List<Checkpoint> checkpoints, List<Long> zoneIds) {
        if (zoneIds == null || zoneIds.isEmpty()) {
            return events;
        }
        return events.stream()
                .filter(
                        event ->
                                checkpointLocator
                                        .findContaining(checkpoints, event.getX(), event.getY())
                                        .map(Checkpoint::getId)
                                        .filter(zoneIds::contains)
                                        .isPresent())
                .toList();
    }

    /**
     * 이벤트 유형별 건수를 Map으로 만든다.
     * 예: {ILLEGAL_PARKING=10, TRASH_DETECTED=3}
     */
    private Map<EventType, Long> countByType(List<DetectedEvent> events) {
        Map<EventType, Long> result = new HashMap<>();
        for (DetectedEvent event : events) {
            result.merge(event.getType(), 1L, Long::sum);
        }
        return result;
    }

    /**
     * 가장 이벤트가 많이 발생한 구역을 찾는다.
     * 좌표가 어떤 체크포인트에도 안 들어가면 집계에서 빠진다.
     * 동점이면 max 비교 결과에 따라 하나가 선택된다.
     */
    private OverviewResponse.Zone findTopZone(List<DetectedEvent> events, List<Checkpoint> checkpoints) {
        Map<Long, Long> countByZoneId = new HashMap<>();
        Map<Long, String> zoneNames = new HashMap<>();
        for (DetectedEvent event : events) {
            checkpointLocator
                    .findContaining(checkpoints, event.getX(), event.getY())
                    .ifPresent(
                            checkpoint -> {
                                countByZoneId.merge(checkpoint.getId(), 1L, Long::sum);
                                zoneNames.putIfAbsent(checkpoint.getId(), checkpoint.getName());
                            });
        }

        return countByZoneId.entrySet().stream()
                .max(Comparator.comparingLong(Map.Entry::getValue))
                .map(
                        entry ->
                                OverviewResponse.Zone.builder()
                                        .zoneId(entry.getKey())
                                        .zoneName(zoneNames.get(entry.getKey()))
                                        .build())
                .orElse(null);
    }

    /**
     * 전체 건수의 현재/이전/증감/증감률을 만든다.
     * diff = current - previous (음수면 감소)
     */
    private OverviewResponse.TotalDelta buildTotalDelta(long current, long previous) {
        long diff = current - previous;
        return OverviewResponse.TotalDelta.builder()
                .current(current)
                .previous(previous)
                .diff(diff)
                .changeRate(calculateChangeRate(previous, diff))
                .build();
    }

    /**
     * 현재 기간에 등장한 유형들만 기준으로, 유형별 증감 목록을 만든다.
     * 이전에만 있고 현재에 없는 유형은 목록에 넣지 않는다. (현재 대시보드 관점)
     */
    private List<OverviewResponse.TypeDelta> buildTypeDeltas(
            Map<EventType, Long> current, Map<EventType, Long> previous) {
        return current.keySet().stream()
                .map(
                        type -> {
                            long currentCount = current.getOrDefault(type, 0L);
                            long previousCount = previous.getOrDefault(type, 0L);
                            long diff = currentCount - previousCount;
                            return OverviewResponse.TypeDelta.builder()
                                    .eventType(type)
                                    .current(currentCount)
                                    .previous(previousCount)
                                    .diff(diff)
                                    .changeRate(calculateChangeRate(previousCount, diff))
                                    .build();
                        })
                .filter(Objects::nonNull)
                .toList();
    }

    /**
     * 증감률(%) 계산.
     * - previous=0, diff=0 → 0%
     * - previous=0, diff>0 → 100% (0에서 새로 생긴 경우의 단순 규칙)
     * - 그 외 → (diff / previous) * 100, 소수 둘째 자리 반올림
     */
    private BigDecimal calculateChangeRate(long previous, long diff) {
        if (previous == 0L) {
            return diff == 0L ? BigDecimal.ZERO : BigDecimal.valueOf(100);
        }
        return BigDecimal.valueOf(diff)
                .multiply(BigDecimal.valueOf(100))
                .divide(BigDecimal.valueOf(previous), 2, RoundingMode.HALF_UP);
    }

    /**
     * KST 기준 "오늘" 구간.
     * 예: 2026-07-29라면 2026-07-29 00:00:00 ~ 2026-07-30 00:00:00
     * to는 다음 날 시작이라, 조회 조건 occurredAt <= to와 함께 쓰면
     * 사실상 오늘 하루치(자정 직전)까지 포함된다.
     */
    private DateRange todayRange() {
        LocalDate today = LocalDate.now(SERVICE_ZONE);
        return new DateRange(today.atStartOfDay(), today.plusDays(1).atStartOfDay());
    }

    /**
     * 현재 조회 기간과 같은 길이의 "바로 이전 기간"을 만든다.
     * 예: from=7/1, to=7/31 → previous = 5/31 ~ 7/1 (같은 초 길이)
     * 이 구간을 이전 동기간으로 보고 증감을 비교한다.
     */
    private DateRange previousRange(LocalDateTime from, LocalDateTime to) {
        long seconds = java.time.Duration.between(from, to).getSeconds();
        return new DateRange(from.minusSeconds(seconds), from);
    }

    /** 시작~끝 시각을 묶어 전달하기 위한 내부용 값 객체 */
    private record DateRange(LocalDateTime from, LocalDateTime to) {}
}
