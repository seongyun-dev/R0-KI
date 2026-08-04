package com.oneloop.patrol.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StopPatrolCommand;
import com.oneloop.patrol.dto.request.PatrolStartRequest;
import com.oneloop.patrol.dto.response.PatrolStartResponse;
import com.oneloop.patrol.dto.response.PatrolStopResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import java.math.BigDecimal;
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
public class PatrolCommandService {

    private final PatrolRepository patrolRepository;
    private final PatrolAiSummaryService patrolAiSummaryService;
    private final ObjectProvider<MqttPublisher> mqttPublisherProvider;
    private final PatrolCommandStateService patrolCommandStateService;

    // 순찰 시작 REST 요청 진입점
    // Patrol을 IN_PROGRESS로 먼저 저장하고, START_PATROL 명령을 MQTT로 발행
    public PatrolStartResponse start(Long apartmentComplexId, PatrolStartRequest request) {
        // prepareStart의 트랜잭션 커밋이 끝난 뒤 발행하므로 즉시 ACK도 commandId를 조회할 수 있다.
        PatrolCommandStateService.PreparedStart prepared =
                patrolCommandStateService.prepareStart(apartmentComplexId, request);
        try {
            publish(prepared.robotKey(), prepared.command());
        } catch (RuntimeException publishFailure) {
            try {
                patrolCommandStateService.failStartPublish(
                        prepared.patrolId(), prepared.commandId());
            } catch (RuntimeException compensationFailure) {
                publishFailure.addSuppressed(compensationFailure);
                log.error(
                        "START_PATROL 발행 실패 보상도 실패했습니다. patrolId={}",
                        prepared.patrolId(),
                        compensationFailure);
            }
            throw publishFailure;
        }
        return prepared.response();
    }

    public PatrolStopResponse stop(Long apartmentComplexId, Long patrolId) {
        // STOP_REQUESTED와 commandId를 먼저 커밋한다. 발행 실패 시 상태를 유지하여 같은 endpoint로 재시도한다.
        PatrolCommandStateService.PreparedStop prepared =
                patrolCommandStateService.prepareStop(apartmentComplexId, patrolId);
        publish(prepared.robotKey(), prepared.command());
        return prepared.response();
    }

    @Transactional
    public void stopAfterReconnect(PatrolRobot robot) {
        // 통신이 끊긴 동안 실제 로봇이 계속 움직였을 수 있다.
        // 실패 처리된 마지막 순찰이 있는 경우 재연결 직후 정지 명령을 다시 보내 실제 정지를 우선한다.
        Patrol patrol =
                patrolRepository.findFirstByRobotIdOrderByStartedAtDesc(robot.getId()).orElse(null);
        if (patrol == null || patrol.getStatus() != PatrolStatus.FAILED) {
            return;
        }

        String commandId = UUID.randomUUID().toString();
        patrol.updateCommandId(commandId);
        publish(robot.getSerialNumber(), StopPatrolCommand.of(commandId));
    }

    // pose 수신 때마다 RobotTelemetryService.updatePose()에서 호출된다.
    // 로봇의 진행중인 순찰이 있고 좌표가 도착지(DESTINATION) 체크포인트 안에 들어오면 자동으로 종료 처리한다.
    public void autoCompleteIfArrived(PatrolRobot robot, BigDecimal x, BigDecimal y) {
        PatrolCommandStateService.PreparedAutoComplete prepared =
                patrolCommandStateService.prepareAutoComplete(robot.getId(), x, y).orElse(null);
        if (prepared == null) {
            return;
        }

        // AI 요약 생성 요청 - 실제 GMS 호출은 트랜잭션 커밋 후 별도 스레드(PatrolCompletedEventListener)에서 처리된다.
        patrolAiSummaryService.requestGeneration(prepared.patrolId());
        publish(prepared.robotKey(), prepared.command());
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
