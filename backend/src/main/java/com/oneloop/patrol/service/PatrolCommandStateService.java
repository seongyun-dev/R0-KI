package com.oneloop.patrol.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StartPatrolCommand;
import com.oneloop.patrol.dto.mqtt.StopPatrolCommand;
import com.oneloop.patrol.dto.request.PatrolStartRequest;
import com.oneloop.patrol.dto.response.PatrolStartResponse;
import com.oneloop.patrol.dto.response.PatrolStopResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 순찰 명령을 발행하기 전에 DB 상태와 commandId를 독립 트랜잭션으로 확정한다.
 *
 * <p>MQTT 발행은 {@link PatrolCommandService}가 이 메서드의 커밋이 끝난 뒤 수행한다. 따라서 로봇이 명령을
 * 받자마자 ACK를 보내도 ACK 처리 트랜잭션이 commandId를 조회할 수 있다.
 */
@Service
@RequiredArgsConstructor
public class PatrolCommandStateService {

    private static final long CONNECTION_TIMEOUT_SECONDS = 15;
    private static final List<PatrolStatus> ACTIVE_PATROL_STATUSES =
            List.of(PatrolStatus.IN_PROGRESS, PatrolStatus.STOP_REQUESTED);

    private final PatrolRepository patrolRepository;
    private final RobotRepository robotRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;

    @Transactional
    public PreparedStart prepareStart(Long apartmentComplexId, PatrolStartRequest request) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                request.getRobotId(), apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        if (patrolRepository.existsByRobotIdAndStatusIn(robot.getId(), ACTIVE_PATROL_STATUSES)) {
            throw new BusinessException(ErrorCode.PATROL_ALREADY_IN_PROGRESS);
        }
        validateReadyForPatrol(robot);
        validateSingleDestination(apartmentComplexId);

        String commandId = UUID.randomUUID().toString();
        Patrol patrol = patrolRepository.save(new Patrol(robot, LocalDateTime.now(), commandId));
        StartPatrolCommand command = StartPatrolCommand.of(commandId, patrol.getId());
        return new PreparedStart(
                patrol.getId(),
                commandId,
                robot.getSerialNumber(),
                command,
                PatrolStartResponse.from(patrol));
    }

    @Transactional
    public PreparedStop prepareStop(Long apartmentComplexId, Long patrolId) {
        Patrol patrol =
                patrolRepository
                        .findByIdAndRobotApartmentComplexId(patrolId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.PATROL_NOT_FOUND));
        if (patrol.getStatus() != PatrolStatus.IN_PROGRESS
                && patrol.getStatus() != PatrolStatus.STOP_REQUESTED) {
            throw new BusinessException(ErrorCode.PATROL_INVALID_STATE);
        }

        // STOP_REQUESTED도 새 commandId로 다시 준비할 수 있어 MQTT 발행 실패 뒤 동일 endpoint 재시도가 가능하다.
        String commandId = UUID.randomUUID().toString();
        patrol.requestStop(commandId);
        return new PreparedStop(
                patrol.getId(),
                commandId,
                patrol.getRobot().getSerialNumber(),
                StopPatrolCommand.of(commandId),
                PatrolStopResponse.from(patrol));
    }

    /** START MQTT 발행 자체가 실패한 경우 활성 순찰이 남지 않도록 별도 트랜잭션으로 보상한다. */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void failStartPublish(Long patrolId, String commandId) {
        patrolRepository
                .findById(patrolId)
                .filter(
                        patrol ->
                                patrol.getStatus() == PatrolStatus.IN_PROGRESS
                                        && Objects.equals(patrol.getCommandId(), commandId))
                .ifPresent(Patrol::fail);
    }

    private void validateReadyForPatrol(PatrolRobot robot) {
        LocalDateTime connectedAt = robot.getLastConnectedAt();
        boolean recentlyConnected =
                connectedAt != null
                        && !connectedAt.isBefore(
                                LocalDateTime.now().minusSeconds(CONNECTION_TIMEOUT_SECONDS));
        boolean modulesNormal =
                robot.getCameraStatus() == SensorStatus.NORMAL
                        && robot.getLidarStatus() == SensorStatus.NORMAL
                        && robot.getMotorStatus() == SensorStatus.NORMAL;
        if (robot.getStatus() != RobotStatus.IDLE || !recentlyConnected || !modulesNormal) {
            throw new BusinessException(ErrorCode.ROBOT_NOT_READY);
        }
    }

    private void validateSingleDestination(Long apartmentComplexId) {
        long destinationCount =
                patrolMapRepository
                        .findByApartmentComplexId(apartmentComplexId)
                        .map(
                                patrolMap ->
                                        checkpointRepository.countByPatrolMapIdAndType(
                                                patrolMap.getId(), CheckpointType.DESTINATION))
                        .orElse(0L);
        if (destinationCount != 1L) {
            throw new BusinessException(ErrorCode.ROBOT_NOT_READY);
        }
    }

    public record PreparedStart(
            Long patrolId,
            String commandId,
            String robotKey,
            StartPatrolCommand command,
            PatrolStartResponse response) {}

    public record PreparedStop(
            Long patrolId,
            String commandId,
            String robotKey,
            StopPatrolCommand command,
            PatrolStopResponse response) {}
}
