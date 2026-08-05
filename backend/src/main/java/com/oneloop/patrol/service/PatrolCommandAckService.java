package com.oneloop.patrol.service;

import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 순찰 시작/종료 명령(START_PATROL/STOP_PATROL)의 ACK를 처리한다. 명령 발행은 PatrolCommandService가 담당한다.
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PatrolCommandAckService {

    private static final int SUPPORTED_SCHEMA_VERSION = 1;
    private static final String START_PATROL = "START_PATROL";
    private static final String STOP_PATROL = "STOP_PATROL";

    private final PatrolRepository patrolRepository;
    private final PatrolAiSummaryService patrolAiSummaryService;

    // ACK 처리 진입점 - MqttInboundHandler가 START_PATROL/STOP_PATROL ACK를 여기로 위임한다.
    @Transactional
    public void handle(String topicRobotKey, CommandAck ack) {
        if (!isValid(ack)) {
            log.warn("[MQTT] 잘못된 순찰 ACK를 무시합니다. robotKey={}, ack={}", topicRobotKey, ack);
            return;
        }

        Patrol patrol = patrolRepository.findByCommandId(ack.commandId()).orElse(null);
        // 순찰에 등록된 실제 로봇과 ACK를 보낸 로봇이 같은지도 다시 확인한다.
        if (patrol == null || !patrol.getRobot().getSerialNumber().equals(topicRobotKey)) {
            log.warn("[MQTT] 순찰과 일치하지 않는 ACK를 무시합니다. robotKey={}, ack={}", topicRobotKey, ack);
            return;
        }

        if (START_PATROL.equals(ack.command())) {
            handleStartAck(patrol, ack);
        } else {
            handleStopAck(patrol, ack);
        }
    }

    // 지원 버전, 명령 종류(START_PATROL/STOP_PATROL), 필수값이 모두 채워졌는지 확인한다.
    private boolean isValid(CommandAck ack) {
        return ack != null
                && ack.schemaVersion() == SUPPORTED_SCHEMA_VERSION
                && (START_PATROL.equals(ack.command()) || STOP_PATROL.equals(ack.command()))
                && ack.commandId() != null
                && ack.status() != null
                && ack.receivedAt() != null;
    }

    // START_PATROL이 SUCCEEDED가 아니면(REJECTED/FAILED 구분 없음) 순찰이 시작되지 못한 것이므로 FAILED로 전환한다.
    private void handleStartAck(Patrol patrol, CommandAck ack) {
        if (ack.status() == CommandAck.AckStatus.SUCCEEDED) {
            log.info(
                    "[MQTT] 순찰 시작 ACK 처리 완료. patrolId={}, commandId={}",
                    patrol.getId(),
                    ack.commandId());
            return;
        }

        if (patrol.getStatus() == PatrolStatus.IN_PROGRESS) {
            patrol.fail();
            log.info(
                    "[MQTT] 순찰 시작 거절/실패로 FAILED 처리. patrolId={}, commandId={}, status={}, reason={}",
                    patrol.getId(),
                    ack.commandId(),
                    ack.status(),
                    ack.reason());
        } else {
            log.warn(
                    "[MQTT] 허용되지 않은 ACK 상태 전환을 무시합니다. patrolId={}, currentStatus={}, status={}",
                    patrol.getId(),
                    patrol.getStatus(),
                    ack.status());
        }
    }

    // STOP_PATROL 성공 ACK가 실제 정지의 확정점이다. 그 전에는 자동 종료도 STOP_REQUESTED로 유지한다.
    private void handleStopAck(Patrol patrol, CommandAck ack) {
        if (ack.status() == CommandAck.AckStatus.SUCCEEDED) {
            if (patrol.getStatus() == PatrolStatus.STOP_REQUESTED) {
                if (patrol.isCompletionRequested()) {
                    patrol.completeRequested();
                    patrolAiSummaryService.requestGeneration(patrol.getId());
                } else {
                    patrol.stop();
                }
            }
            log.info(
                    "[MQTT] 순찰 종료 ACK 처리 완료. patrolId={}, commandId={}",
                    patrol.getId(),
                    ack.commandId());
            return;
        }
        if (patrol.getStatus() == PatrolStatus.STOP_REQUESTED && patrol.isCompletionRequested()) {
            patrol.retryCompletionAfterFailedStop();
        }
        log.warn(
                "[MQTT] 순찰 종료 명령이 거절/실패했습니다. 로봇이 실제로 정지했는지 확인이 필요합니다."
                        + " patrolId={}, commandId={}, status={}, reason={}",
                patrol.getId(),
                ack.commandId(),
                ack.status(),
                ack.reason());
    }
}
