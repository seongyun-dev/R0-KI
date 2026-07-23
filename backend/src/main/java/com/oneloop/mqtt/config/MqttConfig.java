package com.oneloop.mqtt.config;

import com.oneloop.robot.repository.RobotRepository;
import java.util.UUID;
import org.eclipse.paho.client.mqttv3.IMqttClient;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

@Configuration
public class MqttConfig {

    // destroyMethod="disconnect": 앱 종료 시 브로커 연결을 정리
    @Bean(destroyMethod = "disconnect")
    public IMqttClient mqttClient(
            @Value("${app.mqtt.broker-url}") String brokerUrl,
            @Value("${app.mqtt.client-id}") String clientIdPrefix,
            @Value("${app.mqtt.username:}") String username,
            @Value("${app.mqtt.password:}") String password,
            RobotRepository robotRepository)
            throws MqttException {
        // Jetson과 clientId가 겹치면 브로커가 한쪽 연결을 끊어버리므로 UUID로 유일성 보장
        String clientId = clientIdPrefix + "-" + UUID.randomUUID();
        IMqttClient client = new MqttClient(brokerUrl, clientId, new MemoryPersistence());

        MqttConnectOptions options = new MqttConnectOptions();
        // automaticReconnect는 TCP 재연결만 해주고 구독은 안 살아남음 -> 재구독은 MqttInboundHandler#connectComplete에서 처리
        options.setAutomaticReconnect(true);
        options.setCleanSession(true);
        // 인증 정보가 없으면(현재 미확정 상태) 인증 없이 접속 시도
        if (StringUtils.hasText(username)) {
            options.setUserName(username);
            options.setPassword(password.toCharArray());
        }

        client.setCallback(new MqttInboundHandler(client, robotRepository));
        client.connect(options);
        return client;
    }
}
