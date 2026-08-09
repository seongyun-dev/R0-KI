package com.oneloop.patrol.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.response.PageResponse;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolAiSummary;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import com.oneloop.patrol.domain.RoutePosition;
import com.oneloop.patrol.dto.request.PatrolPeriodFilter;
import com.oneloop.patrol.dto.request.PatrolStatusFilter;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.dto.response.PatrolListResponse;
import com.oneloop.patrol.dto.response.PatrolRouteCheckpointResponse;
import com.oneloop.patrol.dto.response.PatrolTimelineResponse;
import com.oneloop.patrol.repository.PatrolAiSummaryRepository;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.patrol.repository.RoutePositionRepository;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.TemporalAdjusters;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PatrolService {

    private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");

    private final PatrolRepository patrolRepository;
    private final RoutePositionRepository routePositionRepository;
    private final PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    private final DetectedEventRepository detectedEventRepository;
    private final PatrolAiSummaryRepository patrolAiSummaryRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final CheckpointLocator checkpointLocator;

    /**
     * 로그인한 관리자의 소속 단지 순찰 기록을 기간과 상태로 필터링하여 조회한다. 페이지에 포함된 모든 순찰의 체크포인트 방문 기록은 한 번의 IN 쿼리로
     * 조회해 순찰마다 개별 쿼리가 실행되는 N+1 문제를 방지한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param period 기간 필터
     * @param status 상태 필터
     * @param pageable 페이지 및 정렬 정보
     * @return 순찰 목록 페이지
     */
    public PageResponse<PatrolListResponse> findAll(
            Long apartmentComplexId,
            PatrolPeriodFilter period,
            PatrolStatusFilter status,
            Pageable pageable) {
        DateTimeRange range = calculateRange(period);
        Page<Patrol> patrols =
                patrolRepository.findAllByFilter(
                        apartmentComplexId,
                        status.toPatrolStatus(),
                        range.fromAt(),
                        range.toAt(),
                        pageable);

        List<Long> patrolIds = patrols.stream().map(Patrol::getId).toList();
        Map<Long, List<PatrolCheckpointVisit>> visitsByPatrolId =
                findVisitsByPatrolId(patrolIds);

        Page<PatrolListResponse> responses =
                patrols.map(
                        patrol ->
                                PatrolListResponse.of(
                                        patrol,
                                        visitsByPatrolId.getOrDefault(
                                                patrol.getId(), List.of())));
        return PageResponse.from(responses);
    }

    public PatrolDetailResponse findDetail(Long apartmentComplexId, Long patrolId) {
        Patrol patrol =
                patrolRepository
                        .findByIdAndRobotApartmentComplexId(patrolId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.PATROL_NOT_FOUND));

        List<RoutePosition> routePositions =
                routePositionRepository.findAllByPatrolIdOrderByRecordedAt(patrolId);
        Optional<PatrolMap> patrolMap = patrolMapRepository.findByApartmentComplexId(apartmentComplexId);
        List<Checkpoint> checkpoints =
                patrolMap
                        .map(map -> checkpointRepository.findAllByPatrolMapId(map.getId()))
                        .orElseGet(List::of);
        List<PatrolRouteCheckpointResponse> route = findRoute(patrolId);
        List<PatrolTimelineResponse> timeline = buildTimeline(patrolId, checkpoints);
        PatrolAiSummary aiSummary = patrolAiSummaryRepository.findByPatrolId(patrolId).orElse(null);

        return PatrolDetailResponse.of(
                patrol,
                patrolMap.map(PatrolMap::getUrl).orElse(null),
                route,
                routePositions,
                timeline,
                aiSummary);
    }

    private List<PatrolRouteCheckpointResponse> findRoute(Long patrolId) {
        return patrolCheckpointVisitRepository
                .findAllByPatrolIdOrderByVisitSequence(patrolId)
                .stream()
                .map(PatrolRouteCheckpointResponse::from)
                .toList();
    }

    private List<PatrolTimelineResponse> buildTimeline(
            Long patrolId, List<Checkpoint> checkpoints) {
        return detectedEventRepository.findAllByPatrolIdOrderByOccurredAt(patrolId).stream()
                .map(
                        event ->
                                PatrolTimelineResponse.of(
                                        event, findCheckpointName(event, checkpoints)))
                .toList();
    }

    private String findCheckpointName(DetectedEvent event, List<Checkpoint> checkpoints) {
        return checkpointLocator.resolveLocationName(checkpoints, event.getX(), event.getY());
    }

    private Map<Long, List<PatrolCheckpointVisit>> findVisitsByPatrolId(
            List<Long> patrolIds) {
        if (patrolIds.isEmpty()) {
            return Map.of();
        }
        return patrolCheckpointVisitRepository.findAllByPatrolIds(patrolIds).stream()
                .collect(
                        Collectors.groupingBy(
                                visit -> visit.getPatrol().getId()));
    }

    private DateTimeRange calculateRange(PatrolPeriodFilter period) {
        ZonedDateTime now = ZonedDateTime.now(SERVICE_ZONE);
        return switch (period) {
            case ALL -> new DateTimeRange(null, null);
            case TODAY -> {
                LocalDate today = now.toLocalDate();
                yield new DateTimeRange(
                        today.atStartOfDay(), today.plusDays(1).atStartOfDay());
            }
            case LAST_7_DAYS ->
                    new DateTimeRange(
                            now.minusDays(7).toLocalDateTime(),
                            now.toLocalDateTime());
            case PREVIOUS_WEEK -> {
                LocalDate thisMonday =
                        now.toLocalDate()
                                .with(
                                        TemporalAdjusters.previousOrSame(
                                                DayOfWeek.MONDAY));
                yield new DateTimeRange(
                        thisMonday.minusWeeks(1).atStartOfDay(),
                        thisMonday.atStartOfDay());
            }
        };
    }

    private record DateTimeRange(LocalDateTime fromAt, LocalDateTime toAt) {}
}
