package com.oneloop.mapping.service;

import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.event.MappingStatusChangedEvent;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.mqtt.dto.CommandAck;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MappingCommandAckService {

    private static final int SUPPORTED_SCHEMA_VERSION = 1;
    private static final String START_MAPPING = "START_MAPPING";

    private final MappingSessionRepository mappingSessionRepository;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public void handle(String topicRobotKey, CommandAck ack) {
        // 지원 버전, 명령 종류, 필수값 및 토픽의 robotKey가 올바른지 먼저 검사한다.
        if (!isValid(ack)) {
            log.warn("[MQTT] 잘못된 매핑 ACK를 무시합니다. robotKey={}, ack={}", topicRobotKey, ack);
            return;
        }

        // commandId로 어느 세션에 대한 ACK인지 특정된다.
        MappingSession session = mappingSessionRepository.findByCommandId(ack.commandId()).orElse(null);
        // 세션에 등록된 실제 로봇과 ACK를 보낸 로봇이 같은지도 다시 확인한다.
        if (session == null || !session.getRobot().getSerialNumber().equals(topicRobotKey)) {
            log.warn("[MQTT] 매핑 세션과 일치하지 않는 ACK를 무시합니다. robotKey={}, ack={}", topicRobotKey, ack);
            return;
        }

        MappingStatus changedStatus = applyResult(session, ack);
        if (changedStatus != null) {
            // DB 상태 변경이 커밋된 후 SSE로 전달할 수 있도록 상태 변경 이벤트를 발행한다.
            eventPublisher.publishEvent(
                    new MappingStatusChangedEvent(session.getId(), changedStatus));
        }

        log.info(
                "[MQTT] 매핑 명령 ACK 처리 완료. sessionId={}, commandId={}, status={}, reason={}",
                session.getId(),
                ack.commandId(),
                ack.status(),
                ack.reason());
    }

    private boolean isValid(CommandAck ack) {
        return ack != null
                && ack.schemaVersion() == SUPPORTED_SCHEMA_VERSION
                && START_MAPPING.equals(ack.command())
                && ack.commandId() != null
                && ack.status() != null
                && ack.receivedAt() != null;
    }

    private MappingStatus applyResult(MappingSession session, CommandAck ack) {
        if (ack.status() == CommandAck.AckStatus.SUCCEEDED) {
            // SUCCEEDED는 실제 LiDAR·SLAM 시작 성공을 의미하며, 중복 ACK는 시작 시각을 변경하지 않는다.
            if (session.getStatus() == MappingStatus.REQUESTED) {
                session.startMapping();
                return MappingStatus.MAPPING;
            } else if (session.getStatus() != MappingStatus.MAPPING) {
                log.warn(
                        "[MQTT] 허용되지 않은 ACK 상태 전환을 무시합니다. sessionId={}, currentStatus={}, status={}",
                        session.getId(),
                        session.getStatus(),
                        ack.status());
            }
            return null;
        }

        // 같은 시작 명령의 REJECTED/FAILED는 REQUESTED와 MAPPING 모두 실패로 닫는다.
        // 이미 완료·취소된 terminal 세션은 뒤늦은 ACK로 되돌리지 않는다.
        if (session.getStatus() == MappingStatus.REQUESTED
                || session.getStatus() == MappingStatus.MAPPING) {
            session.fail();
            return MappingStatus.FAILED;
        } else if (session.getStatus() != MappingStatus.FAILED) {
            log.warn(
                    "[MQTT] 허용되지 않은 ACK 상태 전환을 무시합니다. sessionId={}, currentStatus={}, status={}",
                    session.getId(),
                    session.getStatus(),
                    ack.status());
        }
        return null;
    }
}
