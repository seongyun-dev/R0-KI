package com.oneloop.mqtt.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneloop.mapping.service.MappingCommandAckService;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.service.PatrolCommandAckService;
import com.oneloop.robot.dto.mqtt.RobotPoseMessage;
import com.oneloop.robot.dto.mqtt.RobotStatusMessage;
import com.oneloop.robot.service.RobotTelemetryService;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.paho.client.mqttv3.IMqttClient;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;

@Slf4j
class MqttInboundHandler implements MqttCallbackExtended {

    // IoT팀 MQTT 명세 v1 기준 구독 토픽 (robotKey 자리는 +로 와일드카드)
    private static final String[] SUBSCRIBE_TOPICS = {
        "hanbakwi/v1/robots/+/pose",
        "hanbakwi/v1/robots/+/status",
        "hanbakwi/v1/robots/+/command/ack"
    };
    private static final int QOS = 1;
    private static final String START_MAPPING = "START_MAPPING";
    private static final String STOP_MAPPING = "STOP_MAPPING";
    private static final String START_PATROL = "START_PATROL";
    private static final String STOP_PATROL = "STOP_PATROL";

    private final IMqttClient client;
    private final RobotTelemetryService robotTelemetryService;
    private final MappingCommandAckService mappingCommandAckService;
    private final PatrolCommandAckService patrolCommandAckService;
    // Spring이 관리하는 ObjectMapper 빈이 없어서, 단순 Map 파싱용으로 직접 생성
    private final ObjectMapper objectMapper =
            new ObjectMapper()
                    .findAndRegisterModules()
                    // 로봇이 보낸 +09:00 같은 원래 오프셋을 UTC로 강제 변환하지 않고 그대로 보존합니다.
                    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE);

    MqttInboundHandler(
            IMqttClient client,
            RobotTelemetryService robotTelemetryService,
            MappingCommandAckService mappingCommandAckService,
            PatrolCommandAckService patrolCommandAckService) {
        this.client = client;
        this.robotTelemetryService = robotTelemetryService;
        this.mappingCommandAckService = mappingCommandAckService;
        this.patrolCommandAckService = patrolCommandAckService;
    }

    // 최초 연결/재연결 시마다 호출됨 - 구독
    @Override
    public void connectComplete(boolean reconnect, String serverURI) {
        log.info("[MQTT] 브로커 연결 완료 (재연결={}, serverURI={})", reconnect, serverURI);
        try {
            for (String topic : SUBSCRIBE_TOPICS) {
                client.subscribe(topic, QOS);
            }
            log.info("[MQTT] 토픽 구독 완료: {}", (Object) SUBSCRIBE_TOPICS);
        } catch (MqttException e) {
            log.error("[MQTT] 토픽 구독 실패", e);
        }
    }

    // 연결 끊김 콜백 - automaticReconnect가 재연결 시도
    @Override
    public void connectionLost(Throwable cause) {
        log.warn("[MQTT] 연결 끊김, 자동 재연결 대기", cause);
    }

    // 메시지 수신 진입점 - 토픽 기준으로 각 전용 핸들러에 위임
    @Override
    public void messageArrived(String topic, MqttMessage message) {
        String payload = new String(message.getPayload(), StandardCharsets.UTF_8);

        // command/ack는 PING/START_MAPPING/START_PATROL/STOP_PATROL 공통 스펙(CommandAck)이라
        // 먼저 이 스펙으로 파싱한 뒤 ack.command() 값으로 도메인 서비스에 위임한다.
        if (topic.endsWith("/command/ack")) {
            handleCommandAck(topic, payload);
            return;
        }

        Map<String, Object> parsed;
        try {
            parsed = objectMapper.readValue(payload, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            log.warn("[MQTT] JSON 파싱 실패 topic={}, payload={}", topic, payload, e);
            return;
        }

        if (topic.endsWith("/pose")) {
            handlePose(topic, payload);
        } else if (topic.endsWith("/status")) {
            handleStatus(topic, payload);
        } else {
            log.info("[MQTT] 처리 대상이 아닌 토픽, 로그만 남김. topic={}, payload={}", topic, parsed);
        }
    }

    // pose payload를 RobotPoseMessage로 역직렬화해서 좌표 갱신 서비스에 위임
    private void handlePose(String topic, String payload) {
        try {
            RobotPoseMessage message = objectMapper.readValue(payload, RobotPoseMessage.class);
            if (!hasMatchingRobotKey(topic, message.robotKey())) {
                log.warn(
                        "[MQTT] 토픽과 payload의 robotKey가 다른 pose를 무시합니다. topic={}, payloadRobotKey={}",
                        topic,
                        message.robotKey());
                return;
            }
            robotTelemetryService.updatePose(message);
        } catch (Exception e) {
            log.warn("[MQTT] pose 처리 실패. topic={}, payload={}", topic, payload, e);
        }
    }

    // status payload를 RobotStatusMessage로 역직렬화해서 상태/장애물 갱신 서비스에 위임
    private void handleStatus(String topic, String payload) {
        try {
            RobotStatusMessage message = objectMapper.readValue(payload, RobotStatusMessage.class);
            if (!hasMatchingRobotKey(topic, message.robotKey())) {
                log.warn(
                        "[MQTT] 토픽과 payload의 robotKey가 다른 status를 무시합니다. topic={}, payloadRobotKey={}",
                        topic,
                        message.robotKey());
                return;
            }
            robotTelemetryService.updateStatus(message);
        } catch (Exception e) {
            log.warn("[MQTT] status 처리 실패. topic={}, payload={}", topic, payload, e);
        }
    }

    private boolean hasMatchingRobotKey(String topic, String payloadRobotKey) {
        String[] topicSegments = topic.split("/");
        return topicSegments.length == 5
                && "hanbakwi".equals(topicSegments[0])
                && "v1".equals(topicSegments[1])
                && "robots".equals(topicSegments[2])
                && payloadRobotKey != null
                && topicSegments[3].equals(payloadRobotKey);
    }

    // 공용 CommandAck로 파싱한 뒤 robotKey(토픽 4번째 구간)와 command 값으로 도메인 서비스에 위임
    private void handleCommandAck(String topic, String payload) {
        try {
            CommandAck ack = objectMapper.readValue(payload, CommandAck.class);
            String[] topicSegments = topic.split("/");
            // 정상 토픽: hanbakwi/v1/robots/{robotKey}/command/ack
            if (topicSegments.length != 6) {
                log.warn("[MQTT] 잘못된 커맨드 ACK 토픽을 무시합니다. topic={}", topic);
                return;
            }
            routeCommandAck(topicSegments[3], ack);
        } catch (Exception exception) {
            log.warn("[MQTT] 커맨드 ACK 처리 실패. topic={}, payload={}", topic, payload, exception);
        }
    }

    private void routeCommandAck(String robotKey, CommandAck ack) {
        String command = ack.command();
        if (START_MAPPING.equals(command) || STOP_MAPPING.equals(command)) {
            mappingCommandAckService.handle(robotKey, ack);
        } else if (START_PATROL.equals(command) || STOP_PATROL.equals(command)) {
            patrolCommandAckService.handle(robotKey, ack);
        } else {
            // PING 등 아직 처리 대상이 아닌 커맨드 ACK는 로그만 남김
            log.info("[MQTT] 처리 대상이 아닌 커맨드 ACK, 로그만 남김. robotKey={}, ack={}", robotKey, ack);
        }
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
        // 발행 확인 콜백 - 발행은 MqttPublisher에서 동기 publish로 처리하므로 여기선 사용 안 함
    }
}
