package com.oneloop.mqtt.config;

import com.oneloop.robot.repository.RobotRepository;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.paho.client.mqttv3.IMqttClient;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.util.StringUtils;

// test 프로파일(contextLoads 등)에서는 실제 브로커가 없어 연결이 실패하므로 빈 자체를 안 만듦
@Slf4j
@Profile("!test")
@Configuration
public class MqttConfig {

    private static final long RETRY_DELAY_SECONDS = 10;

    // destroyMethod="disconnect": 앱 종료 시 브로커 연결을 정리
    @Bean(destroyMethod = "disconnect")
    public IMqttClient mqttClient(
            @Value("${mqtt.broker-uri}") String brokerUrl,
            @Value("${app.mqtt.client-id}") String clientIdPrefix,
            @Value("${mqtt.username:}") String username,
            @Value("${mqtt.password:}") String password,
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
        connectWithRetry(client, options);
        return client;
    }

    // 최초 연결이 실패해도 앱 부팅은 계속되도록 하고, 백그라운드에서 주기적으로 재시도한다.
    // (automaticReconnect는 "한 번 연결된 뒤 끊긴 경우"만 재연결해주고, 최초 연결 실패는 재시도해주지 않음)
    private void connectWithRetry(IMqttClient client, MqttConnectOptions options) {
        try {
            client.connect(options);
            log.info("[MQTT] 브로커 연결 성공");
            return;
        } catch (MqttException e) {
            log.error(
                    "[MQTT] 최초 연결 실패, {}초마다 재시도합니다 (앱은 정상 기동함)",
                    RETRY_DELAY_SECONDS,
                    e);
        }

        ScheduledExecutorService retryExecutor =
                Executors.newSingleThreadScheduledExecutor(
                        runnable -> {
                            Thread thread = new Thread(runnable, "mqtt-connect-retry");
                            thread.setDaemon(true);
                            return thread;
                        });
        retryExecutor.scheduleWithFixedDelay(
                () -> {
                    try {
                        client.connect(options);
                        log.info("[MQTT] 재연결 성공");
                        retryExecutor.shutdown();
                    } catch (MqttException retryException) {
                        log.warn("[MQTT] 재연결 시도 실패: {}", retryException.getMessage());
                    }
                },
                RETRY_DELAY_SECONDS,
                RETRY_DELAY_SECONDS,
                TimeUnit.SECONDS);
    }
}
