package com.oneloop.robot.service;

import com.oneloop.mqtt.MqttPublisher;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

// 로봇 REST 인증용 서비스 토큰 생성 + MQTT(SET_TOKEN 커맨드) 발행을 전담하는 컴포넌트
@Component
@RequiredArgsConstructor
public class RobotServiceTokenPublisher {

    // SET_TOKEN 커맨드의 유효시간.
    private static final long COMMAND_TTL_HOURS = 24;

    private final Optional<MqttPublisher> mqttPublisher;

    // 토큰 생성
    public String generate() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    // 로봇이 발급 시점에 연결되어 있지 않아도 나중에 command 토픽을 구독하면 받을 수 있도록 retained로 발행한다.
    public void publish(String robotKey, String serviceToken) {
        OffsetDateTime issuedAt = OffsetDateTime.now(ZoneId.of("Asia/Seoul"));
        OffsetDateTime expiresAt = issuedAt.plusHours(COMMAND_TTL_HOURS);
        String commandId = UUID.randomUUID().toString();
        String payload =
                """
                {
                  "schemaVersion": 1,
                  "commandId": "%s",
                  "command": "SET_TOKEN",
                  "token": "%s",
                  "issuedAt": "%s",
                  "expiresAt": "%s"
                }
                """
                        .formatted(
                                commandId,
                                serviceToken,
                                issuedAt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                                expiresAt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME));

        mqttPublisher.ifPresent(
                publisher -> publisher.publishRetained("hanbakwi/v1/robots/" + robotKey + "/command", payload));
    }
}
