package com.oneloop.mqtt;

import java.nio.charset.StandardCharsets;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.paho.client.mqttv3.IMqttClient;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class MqttPublisher {

    private static final int QOS = 1;

    private final IMqttClient mqttClient;

    // 나중에 순찰 시작/종료(PatrolService) 등에서 그대로 호출할 범용 발행 메서드
    public void publish(String topic, String payload) {
        try {
            MqttMessage message = new MqttMessage(payload.getBytes(StandardCharsets.UTF_8));
            message.setQos(QOS);
            mqttClient.publish(topic, message);
            log.info("[MQTT] 발행 완료 topic={}, payload={}", topic, payload);
        } catch (MqttException e) {
            // 호출부가 아직 없어 지금은 로그만 남김 - 실제 사용처 붙을 때 실패 처리 다시 판단
            log.error("[MQTT] 발행 실패 topic={}, payload={}", topic, payload, e);
        }
    }
}
