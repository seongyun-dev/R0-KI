package com.oneloop.mqtt.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oneloop.mapping.dto.mqtt.MappingCommandAck;
import com.oneloop.mapping.service.MappingCommandAckService;
import com.oneloop.robot.repository.RobotRepository;
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

    private final IMqttClient client;
    private final RobotRepository robotRepository;
    private final MappingCommandAckService mappingCommandAckService;
    // Spring이 관리하는 ObjectMapper 빈이 없어서, 단순 Map 파싱용으로 직접 생성
    private final ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

    MqttInboundHandler(IMqttClient client, RobotRepository robotRepository,
            MappingCommandAckService mappingCommandAckService) {
        this.client = client;
        this.robotRepository = robotRepository;
        this.mappingCommandAckService = mappingCommandAckService;
    }

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

    @Override
    public void connectionLost(Throwable cause) {
        log.warn("[MQTT] 연결 끊김, 자동 재연결 대기", cause);
    }

    @Override
    public void messageArrived(String topic, MqttMessage message) {
        String payload = new String(message.getPayload(), StandardCharsets.UTF_8);

        // 이번 단계는 엔티티 갱신 없이, 역직렬화/robotKey 매칭까지만 확인 (실제 반영은 다음 단계)
        Map<String, Object> parsed;
        try {
            parsed = objectMapper.readValue(payload, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            log.warn("[MQTT] JSON 파싱 실패 topic={}, payload={}", topic, payload, e);
            return;
        }

        // 공통 ACK 토픽에서는 command 값으로 지도 생성 ACK를 구분한다.
        if (topic.endsWith("/command/ack")
                && "START_MAPPING".equals(String.valueOf(parsed.get("command")))) {
            handleMappingCommandAck(topic, payload);
            return;
        }

        Object robotKey = parsed.get("robotKey");
        boolean known =
                robotKey != null
                        && robotRepository.findBySerialNumber(String.valueOf(robotKey)).isPresent();
        log.info("[MQTT] topic={}, robotKey={}, known={}, payload={}", topic, robotKey, known, parsed);
    }

    private void handleMappingCommandAck(String topic, String payload) {
        try {
            MappingCommandAck ack = objectMapper.readValue(payload, MappingCommandAck.class);
            String[] topicSegments = topic.split("/");
            // 정상 토픽: hanbakwi/v1/robots/{robotKey}/command/ack
            if (topicSegments.length != 6) {
                log.warn("[MQTT] 잘못된 매핑 ACK 토픽을 무시합니다. topic={}", topic);
                return;
            }
            // 네 번째 토픽 구간의 robotKey와 ACK 내용을 서비스에서 교차 검증한다.
            mappingCommandAckService.handle(topicSegments[3], ack);
        } catch (Exception exception) {
            log.warn("[MQTT] 매핑 ACK 처리 실패. topic={}, payload={}", topic, payload, exception);
        }
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
        // 발행 확인 콜백 - 발행은 MqttPublisher에서 동기 publish로 처리하므로 여기선 사용 안 함
    }
}
