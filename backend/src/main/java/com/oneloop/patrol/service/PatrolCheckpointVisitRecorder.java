package com.oneloop.patrol.service;

import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/** 순찰 중 pose가 현재 활성 구역에 들어온 순간을 기존 체크포인트 방문 이력에 기록한다. */
@Service
@RequiredArgsConstructor
public class PatrolCheckpointVisitRecorder {

    private final CheckpointRepository checkpointRepository;
    private final PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    private final CheckpointLocator checkpointLocator;

    /**
     * 호출자는 해당 순찰 행을 비관적 쓰기 잠금으로 획득한 트랜잭션 안에 있어야 한다. 이 잠금이 같은 순찰의
     * visitSequence 계산과 저장을 직렬화한다.
     */
    public void recordEntry(
            Patrol patrol,
            PatrolMap patrolMap,
            BigDecimal x,
            BigDecimal y,
            LocalDateTime visitedAt) {
        if (patrol.getStatus() != PatrolStatus.IN_PROGRESS
                || patrol.getStartedAt() == null
                || visitedAt == null
                || visitedAt.isBefore(patrol.getStartedAt())) {
            return;
        }

        List<Checkpoint> checkpoints =
                checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(patrolMap.getId());
        Checkpoint currentCheckpoint =
                checkpointLocator.findContaining(checkpoints, x, y).orElse(null);
        if (currentCheckpoint == null) {
            return;
        }

        PatrolCheckpointVisit latestVisit =
                patrolCheckpointVisitRepository
                        .findFirstByPatrolIdOrderByVisitSequenceDesc(patrol.getId())
                        .orElse(null);
        if (latestVisit != null
                && (visitedAt.isBefore(latestVisit.getVisitedAt())
                        || Objects.equals(
                                latestVisit.getCheckpoint().getId(), currentCheckpoint.getId()))) {
            return;
        }

        int nextSequence = latestVisit == null ? 1 : latestVisit.getVisitSequence() + 1;
        patrolCheckpointVisitRepository.save(
                new PatrolCheckpointVisit(patrol, currentCheckpoint, nextSequence, visitedAt));
    }
}
