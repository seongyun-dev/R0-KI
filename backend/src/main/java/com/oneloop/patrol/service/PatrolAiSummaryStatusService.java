package com.oneloop.patrol.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolAiSummary;
import com.oneloop.patrol.domain.AiSummaryGenerationStatus;
import com.oneloop.patrol.dto.internal.PatrolSummaryInput;
import com.oneloop.patrol.repository.PatrolAiSummaryRepository;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.patrol.repository.PatrolRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class PatrolAiSummaryStatusService {

    private final PatrolRepository patrolRepository;
    private final PatrolAiSummaryRepository patrolAiSummaryRepository;
    private final PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    private final DetectedEventRepository detectedEventRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;

    /**
     * 요약 상태를 PROCESSING으로 바꾸고 GMS에 전달할 데이터를 조회한다.
     *
     * <p>이 메서드의 트랜잭션은 데이터 조회와 상태 저장이 끝나면 바로 종료한다. GMS 응답을 기다리는 동안 DB 커넥션과 트랜잭션을 계속 점유하지 않기 위해 외부
     * API 호출은 이 메서드 밖에서 수행한다.
     */
    @Transactional
    public Optional<PatrolSummaryInput> prepareGeneration(Long patrolId) {
        Patrol patrol =
                patrolRepository
                        .findById(patrolId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.PATROL_NOT_FOUND));
        PatrolAiSummary aiSummary =
                patrolAiSummaryRepository
                        .findByPatrolId(patrolId)
                        .orElseGet(
                                () ->
                                        patrolAiSummaryRepository.save(
                                                new PatrolAiSummary(patrol)));

        if (aiSummary.getGenerationStatus() == AiSummaryGenerationStatus.PROCESSING
                || aiSummary.getGenerationStatus() == AiSummaryGenerationStatus.COMPLETED) {
            return Optional.empty();
        }

        aiSummary.startGeneration();

        List<Checkpoint> checkpoints =
                patrolMapRepository
                        .findByApartmentComplexId(patrol.getRobot().getApartmentComplex().getId())
                        .map(map -> checkpointRepository.findAllByPatrolMapId(map.getId()))
                        .orElseGet(List::of);

        List<PatrolSummaryInput.VisitedCheckpoint> visitedCheckpoints =
                patrolCheckpointVisitRepository
                        .findAllByPatrolIdOrderByVisitSequence(patrolId)
                        .stream()
                        .map(
                                visit ->
                                        PatrolSummaryInput.VisitedCheckpoint.builder()
                                                .sequence(visit.getVisitSequence())
                                                .checkpointType(visit.getCheckpoint().getType())
                                                .checkpointName(visit.getCheckpoint().getName())
                                                .visitedAt(visit.getVisitedAt())
                                                .build())
                        .toList();

        List<PatrolSummaryInput.DetectedEventInput> events =
                detectedEventRepository.findAllByPatrolIdOrderByOccurredAt(patrolId).stream()
                        .map(event -> toEventInput(event, checkpoints))
                        .toList();

        return Optional.of(
                PatrolSummaryInput.builder()
                        .patrolId(patrol.getId())
                        .robotName(patrol.getRobot().getName())
                        .startedAt(patrol.getStartedAt())
                        .endedAt(patrol.getEndedAt())
                        .durationMinutes(toMinutes(patrol.getTotalDuration()))
                        .startBatteryLevel(patrol.getStartBatteryLevel())
                        .endBatteryLevel(patrol.getEndBatteryLevel())
                        .visitedCheckpoints(visitedCheckpoints)
                        .events(events)
                        .build());
    }

    /** GMS가 반환한 요약을 저장하고 생성 상태를 COMPLETED로 변경한다. */
    @Transactional
    public void completeGeneration(Long patrolId, String summaryContent) {
        findAiSummary(patrolId).completeGeneration(summaryContent);
    }

    /** GMS 호출 또는 응답 처리에 실패한 요약의 생성 상태를 FAILED로 변경한다. */
    @Transactional
    public void failGeneration(Long patrolId) {
        patrolAiSummaryRepository
                .findByPatrolId(patrolId)
                .ifPresent(PatrolAiSummary::failGeneration);
    }

    private PatrolAiSummary findAiSummary(Long patrolId) {
        return patrolAiSummaryRepository
                .findByPatrolId(patrolId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));
    }

    private PatrolSummaryInput.DetectedEventInput toEventInput(
            DetectedEvent event, List<Checkpoint> checkpoints) {
        return PatrolSummaryInput.DetectedEventInput.builder()
                .eventId(event.getId())
                .eventType(event.getType())
                .title(event.getTitle())
                .details(event.getDetails())
                .riskLevel(event.getRiskLevel())
                .occurredAt(event.getOccurredAt())
                .checkpointName(findCheckpointName(event, checkpoints))
                .processingStatus(event.getProcessingStatus())
                .build();
    }

    private String findCheckpointName(DetectedEvent event, List<Checkpoint> checkpoints) {
        if (event.getX() == null || event.getY() == null) {
            return null;
        }
        return checkpoints.stream()
                .filter(checkpoint -> contains(checkpoint, event.getX(), event.getY()))
                .findFirst()
                .map(Checkpoint::getName)
                .orElse(null);
    }

    private boolean contains(Checkpoint checkpoint, BigDecimal x, BigDecimal y) {
        return x.compareTo(checkpoint.getMinX()) >= 0
                && x.compareTo(checkpoint.getMaxX()) <= 0
                && y.compareTo(checkpoint.getMinY()) >= 0
                && y.compareTo(checkpoint.getMaxY()) <= 0;
    }

    private Integer toMinutes(Integer totalDurationSeconds) {
        return totalDurationSeconds == null ? null : totalDurationSeconds / 60;
    }
}
