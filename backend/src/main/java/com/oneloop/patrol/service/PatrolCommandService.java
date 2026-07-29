package com.oneloop.patrol.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StartPatrolCommand;
import com.oneloop.patrol.dto.mqtt.StopPatrolCommand;
import com.oneloop.patrol.dto.request.PatrolStartRequest;
import com.oneloop.patrol.dto.response.PatrolStartResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 순찰 시작/종료 등 로봇에 MQTT 명령을 발행하는 쓰기 전용 로직.
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PatrolCommandService {

    private final PatrolRepository patrolRepository;
    private final RobotRepository robotRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final CheckpointLocator checkpointLocator;
    private final PatrolAiSummaryService patrolAiSummaryService;
    private final ObjectProvider<MqttPublisher> mqttPublisherProvider;

    // 순찰 시작 REST 요청 진입점
    // Patrol을 IN_PROGRESS로 먼저 저장하고, START_PATROL 명령을 MQTT로 발행
    @Transactional
    public PatrolStartResponse start(Long apartmentComplexId, PatrolStartRequest request) {
        // 로그인한 관리자의 단지에 속하고 삭제되지 않은 로봇만 순찰을 시작할 수 있다.
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                request.getRobotId(), apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        if (patrolRepository.existsByRobotIdAndStatus(robot.getId(), PatrolStatus.IN_PROGRESS)) {
            throw new BusinessException(ErrorCode.PATROL_ALREADY_IN_PROGRESS);
        }

        // commandId는 MQTT 명령과 IoT가 돌려주는 ACK가 같은 명령인지 확인하기 위해 저장한다.
        String commandId = UUID.randomUUID().toString();
        Patrol patrol = patrolRepository.save(new Patrol(robot, LocalDateTime.now(), commandId));

        StartPatrolCommand command = StartPatrolCommand.of(commandId, patrol.getId());
        publish(robot.getSerialNumber(), command);

        return PatrolStartResponse.from(patrol);
    }

    // pose 수신 때마다 RobotTelemetryService.updatePose()에서 호출된다.
    // 로봇의 진행중인 순찰이 있고 좌표가 도착지(DESTINATION) 체크포인트 안에 들어오면 자동으로 종료 처리한다.
    @Transactional
    public void autoCompleteIfArrived(PatrolRobot robot, BigDecimal x, BigDecimal y) {
        Patrol patrol =
                patrolRepository.findFirstByRobotIdOrderByStartedAtDesc(robot.getId()).orElse(null);
        // 최신 순찰이 없거나 이미 진행중이 아니면(완료/실패 처리됨) 볼 것 없음 - pose는 1초 주기라 매번 재확인함
        if (patrol == null || patrol.getStatus() != PatrolStatus.IN_PROGRESS) {
            return;
        }

        Checkpoint destination = findDestinationCheckpoint(robot);
        if (destination == null || checkpointLocator.findContaining(List.of(destination), x, y).isEmpty()) {
            return;
        }

        patrol.complete();
        // AI 요약 생성 요청 - 실제 GMS 호출은 트랜잭션 커밋 후 별도 스레드(PatrolCompletedEventListener)에서 처리된다.
        patrolAiSummaryService.requestGeneration(patrol.getId());

        // STOP_PATROL은 새 명령이므로 commandId를 새로 발급해 ACK 매칭에 사용한다.
        String commandId = UUID.randomUUID().toString();
        patrol.updateCommandId(commandId);
        publish(robot.getSerialNumber(), StopPatrolCommand.of(commandId));
    }

    // 도착지 찾기
    private Checkpoint findDestinationCheckpoint(PatrolRobot robot) {
        PatrolMap patrolMap =
                patrolMapRepository
                        .findByApartmentComplexId(robot.getApartmentComplex().getId())
                        .orElse(null);
        if (patrolMap == null) {
            log.warn("[MQTT] 단지에 등록된 지도가 없어 순찰 자동 종료 판정을 건너뜁니다. robotId={}", robot.getId());
            return null;
        }

        return checkpointRepository.findAllByPatrolMapId(patrolMap.getId()).stream()
                .filter(checkpoint -> checkpoint.getType() == CheckpointType.DESTINATION)
                .findFirst()
                .orElse(null);
    }

    // 명령 DTO를 지정한 robotKey의 공통 명령 토픽으로 발행하는 공용 헬퍼
    private void publish(String robotKey, Object command) {
        MqttPublisher mqttPublisher = mqttPublisherProvider.getIfAvailable();
        if (mqttPublisher == null) {
            throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
        }
        mqttPublisher.publishCommand(robotKey, command);
    }
}
