package com.oneloop.mqtt;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

// MQTT 발행 연결 확인용 임시 클래스 - 확인 끝나면 삭제 (실제 발행은 순찰 시작/종료 기능에서 호출)
@Profile("mqtt-spike")
@Component
@RequiredArgsConstructor
public class MqttSpikeTestRunner implements CommandLineRunner {

    // IoT팀 스펙 문서 예시 로봇키. 응답 없으면 IoT팀에 실제 로봇키 확인 필요
    private static final String TEST_ROBOT_KEY = "ROKI-01";

    private final MqttPublisher mqttPublisher;

    @Override
    public void run(String... args) {
        OffsetDateTime issuedAt = OffsetDateTime.now(ZoneId.of("Asia/Seoul"));
        OffsetDateTime expiresAt = issuedAt.plusSeconds(10);
        String commandId = UUID.randomUUID().toString();

        String payload =
                """
                {
                  "schemaVersion": 1,
                  "commandId": "%s",
                  "command": "PING",
                  "issuedAt": "%s",
                  "expiresAt": "%s"
                }
                """
                        .formatted(
                                commandId,
                                issuedAt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                                expiresAt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME));

        mqttPublisher.publish("hanbakwi/v1/robots/" + TEST_ROBOT_KEY + "/command", payload);
    }
}
