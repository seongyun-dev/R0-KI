package com.oneloop.mapping.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.mapping.dto.mqtt.StartMappingCommand;
import com.oneloop.mapping.dto.request.MappingStartRequest;
import com.oneloop.mapping.dto.response.MappingStartResponse;
import com.oneloop.mqtt.MqttPublisher;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class MappingSessionService {

    private final ObjectProvider<MqttPublisher> mqttPublisherProvider;
    private final MappingCommandStateService mappingCommandStateService;

    public MappingStartResponse start(Long apartmentComplexId, MappingStartRequest request) {
        MappingCommandStateService.PreparedMappingStart prepared =
                mappingCommandStateService.prepareStart(apartmentComplexId, request);
        try {
            publishStartMappingCommand(prepared.robotKey(), prepared.command());
        } catch (RuntimeException publishFailure) {
            try {
                mappingCommandStateService.failStartPublish(
                        prepared.mappingSessionId(), prepared.commandId());
            } catch (RuntimeException compensationFailure) {
                publishFailure.addSuppressed(compensationFailure);
                log.error(
                        "START_MAPPING 발행 실패 보상도 실패했습니다. mappingSessionId={}",
                        prepared.mappingSessionId(),
                        compensationFailure);
            }
            throw publishFailure;
        }
        return prepared.response();
    }

    private void publishStartMappingCommand(String robotKey, StartMappingCommand command) {
        // test 프로파일에는 실제 MQTT 빈이 없으므로 ObjectProvider를 통해 존재 여부를 확인한다.
        MqttPublisher mqttPublisher = mqttPublisherProvider.getIfAvailable();
        if (mqttPublisher == null) {
            throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
        }
        mqttPublisher.publishCommand(robotKey, command);
    }
}
