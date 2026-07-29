package com.oneloop.analytics.service;

import com.oneloop.analytics.dto.response.OverviewResponse;
import com.oneloop.analytics.repository.AnalyticsRepository;
import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
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
        boolean hasEventTypes = eventTypes != null && !eventTypes.isEmpty();
        boolean hasRobotIds = robotIds != null && !robotIds.isEmpty();

        return analyticsRepository.findEventsForOverview(
                apartmentComplexId,
                from,
                to,
                hasEventTypes,
                // hasEventTypes=false면 쿼리에서 IN 조건을 타지 않음. 바인딩만 필요해서 더미 사용
                hasEventTypes ? eventTypes : List.of(EventType.EMERGENCY),
                hasRobotIds,
                // 존재하지 않을 로봇 ID. hasRobotIds=false면 IN 조건 미적용
                hasRobotIds ? robotIds : List.of(-1L));
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
