package com.oneloop.patrol.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolAiSummary;
import com.oneloop.patrol.domain.RoutePosition;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.dto.response.PatrolRouteCheckpointResponse;
import com.oneloop.patrol.dto.response.PatrolTimelineResponse;
import com.oneloop.patrol.repository.PatrolAiSummaryRepository;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.patrol.repository.RoutePositionRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PatrolService {

    private final PatrolRepository patrolRepository;
    private final RoutePositionRepository routePositionRepository;
    private final PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    private final DetectedEventRepository detectedEventRepository;
    private final PatrolAiSummaryRepository patrolAiSummaryRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;

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
        if (event.getX() == null || event.getY() == null) {
            return null;
        }
        return findCheckpoint(checkpoints, event.getX(), event.getY())
                .map(checkpoint -> checkpoint.getType().getDisplayName())
                .orElse(null);
    }

    private Optional<Checkpoint> findCheckpoint(
            List<Checkpoint> checkpoints, BigDecimal x, BigDecimal y) {
        return checkpoints.stream().filter(checkpoint -> contains(checkpoint, x, y)).findFirst();
    }

    private boolean contains(Checkpoint checkpoint, BigDecimal x, BigDecimal y) {
        return x.compareTo(checkpoint.getMinX()) >= 0
                && x.compareTo(checkpoint.getMaxX()) <= 0
                && y.compareTo(checkpoint.getMinY()) >= 0
                && y.compareTo(checkpoint.getMaxY()) <= 0;
    }
}
