package com.oneloop.event.service;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.ResumePatrolCommand;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class EmergencyPatrolResumeService {

    private final ObjectProvider<MqttPublisher> mqttPublisherProvider;

    /**
     * Resume only the same active patrol that owns the completed emergency event.
     * Historical, non-emergency and already-ended patrol events never move a robot.
     */
    public boolean resumeIfEligible(DetectedEvent event) {
        if (event.getType() != EventType.EMERGENCY) {
            return false;
        }
        Patrol patrol = event.getPatrol();
        if (patrol == null || patrol.getStatus() != PatrolStatus.IN_PROGRESS) {
            return false;
        }
        if (!patrol.getRobot().getId().equals(event.getRobot().getId())) {
            log.warn(
                    "응급 이벤트와 순찰의 로봇이 달라 재개하지 않습니다. eventId={}, patrolId={}",
                    event.getId(),
                    patrol.getId());
            return false;
        }

        MqttPublisher mqttPublisher = mqttPublisherProvider.getIfAvailable();
        if (mqttPublisher == null) {
            throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
        }
        String commandId = UUID.randomUUID().toString();
        mqttPublisher.publishCommand(
                patrol.getRobot().getSerialNumber(),
                ResumePatrolCommand.of(commandId, patrol.getId()));
        log.info(
                "[MQTT] 응급 처리완료 순찰 재개 명령 발행. eventId={}, patrolId={}, commandId={}",
                event.getId(),
                patrol.getId(),
                commandId);
        return true;
    }
}
