package com.oneloop.mqtt;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import java.nio.charset.StandardCharsets;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.paho.client.mqttv3.IMqttClient;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

// MqttConfig의 IMqttClient 빈이 test 프로파일엔 없어서 이 빈도 같이 제외
@Slf4j
@Profile("!test")
@Component
@RequiredArgsConstructor
public class MqttPublisher {

    private static final int QOS = 1;
    // 모든 로봇 명령은 공통 토픽으로 보내고 IoT는 payload의 command 값으로 기능을 구분한다.
    private static final String ROBOT_COMMAND_TOPIC = "hanbakwi/v1/robots/%s/command";

    private final IMqttClient mqttClient;
    private final ObjectMapper objectMapper =
            new ObjectMapper()
                    .findAndRegisterModules()
                    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    // 순찰/지도 생성 등 도메인 서비스가 로봇 명령 DTO를 그대로 넘기면 공통 명령 토픽으로 직렬화해 발행한다.
    public void publishCommand(String robotKey, Object command) {
        try {
            publish(ROBOT_COMMAND_TOPIC.formatted(robotKey), objectMapper.writeValueAsString(command));
        } catch (JsonProcessingException exception) {
            throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
        }
    }

    // 범용 발행 메서드
    public void publish(String topic, String payload) {
        send(topic, payload, false);
    }

    // 브로커가 마지막 메시지를 저장해뒀다가, 나중에 구독하는 클라이언트에게 즉시 재전달한다.
    // (로봇이 발행 시점에 연결되어 있지 않아도 나중에 구독하면 받을 수 있음 - 서비스 토큰 최초 전달 등에 사용)
    public void publishRetained(String topic, String payload) {
        send(topic, payload, true);
    }

    private void send(String topic, String payload, boolean retained) {
        try {
            MqttMessage message = new MqttMessage(payload.getBytes(StandardCharsets.UTF_8));
            message.setQos(QOS);
            message.setRetained(retained);
            mqttClient.publish(topic, message);
            log.info("[MQTT] 발행 완료 topic={}, retained={}, payload={}", topic, retained, payload);
        } catch (MqttException e) {
            // 호출부가 아직 없어 지금은 로그만 남김 - 실제 사용처 붙을 때 실패 처리 다시 판단
            log.error("[MQTT] 발행 실패 topic={}, payload={}", topic, payload, e);
        }
    }
}
