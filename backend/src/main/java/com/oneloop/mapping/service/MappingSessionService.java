package com.oneloop.mapping.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.dto.mqtt.StartMappingCommand;
import com.oneloop.mapping.dto.request.MappingStartRequest;
import com.oneloop.mapping.dto.response.MappingStartResponse;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MappingSessionService {

    // 모든 로봇 명령은 공통 토픽으로 보내고 IoT는 payload의 command 값으로 기능을 구분한다.
    private static final String ROBOT_COMMAND_TOPIC = "hanbakwi/v1/robots/%s/command";
    // 한 로봇이 동시에 두 개의 지도를 생성하지 못하도록 중복 요청을 막는 상태 목록이다.
    private static final List<MappingStatus> ACTIVE_STATUSES =
            List.of(MappingStatus.REQUESTED, MappingStatus.MAPPING);

    private final MappingSessionRepository mappingSessionRepository;
    private final RobotRepository robotRepository;
    private final ObjectProvider<MqttPublisher> mqttPublisherProvider;
    private final ObjectMapper objectMapper =
            new ObjectMapper()
                    .findAndRegisterModules()
                    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    @Transactional
    public MappingStartResponse start(Long apartmentComplexId, MappingStartRequest request) {
        // 로그인한 관리자의 단지에 속하고 삭제되지 않은 로봇만 지도 생성을 요청할 수 있다.
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                request.getRobotId(), apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        // REQUESTED 또는 MAPPING 세션이 있으면 같은 로봇에 새로운 세션을 만들지 않는다.
        if (mappingSessionRepository.existsByRobotIdAndStatusIn(robot.getId(), ACTIVE_STATUSES)) {
            throw new BusinessException(ErrorCode.MAPPING_SESSION_ALREADY_ACTIVE);
        }

        // commandId는 MQTT 명령과 IoT가 돌려주는 ACK가 같은 명령인지 확인하기 위해 저장한다.
        String commandId = UUID.randomUUID().toString();
        MappingSession session =
                mappingSessionRepository.save(
                        new MappingSession(robot.getApartmentComplex(), robot, commandId));

        // 저장 후 생성된 mappingSessionId를 명령에 담아 이후 상태와 지도 파일을 같은 세션에 연결한다.
        StartMappingCommand command = StartMappingCommand.of(commandId, session.getId());
        publishStartMappingCommand(robot.getSerialNumber(), command);

        return MappingStartResponse.from(session);
    }

    private void publishStartMappingCommand(String robotKey, StartMappingCommand command) {
        // test 프로파일에는 실제 MQTT 빈이 없으므로 ObjectProvider를 통해 존재 여부를 확인한다.
        MqttPublisher mqttPublisher = mqttPublisherProvider.getIfAvailable();
        if (mqttPublisher == null) {
            throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
        }

        try {
            // 명령 DTO를 UTF-8 JSON으로 직렬화하여 대상 로봇의 공통 명령 토픽으로 발행한다.
            mqttPublisher.publish(
                    ROBOT_COMMAND_TOPIC.formatted(robotKey),
                    objectMapper.writeValueAsString(command));
        } catch (JsonProcessingException exception) {
            throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
        }
    }
}
