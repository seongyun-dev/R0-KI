package com.oneloop.mqtt.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import com.oneloop.mapping.service.MappingCommandAckService;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.service.PatrolCommandAckService;
import com.oneloop.robot.dto.mqtt.RobotPoseMessage;
import com.oneloop.robot.dto.mqtt.RobotStatusMessage;
import com.oneloop.robot.service.RobotTelemetryService;
import java.nio.charset.StandardCharsets;
import org.eclipse.paho.client.mqttv3.IMqttClient;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MqttInboundHandlerTest {

    @Mock private IMqttClient client;
    @Mock private RobotTelemetryService robotTelemetryService;
    @Mock private MappingCommandAckService mappingCommandAckService;
    @Mock private PatrolCommandAckService patrolCommandAckService;

    @Test
    void dropsPoseWhenTopicAndPayloadRobotKeysDiffer() {
        handler()
                .messageArrived(
                        "hanbakwi/v1/robots/test-101/pose",
                        mqttMessage(
                                """
                                {"schemaVersion":1,"robotKey":"robot17","x":1.0,"y":2.0,
                                 "heading":0.0,"timestamp":"2026-08-04T12:00:00+09:00"}
                                """));

        verifyNoInteractions(robotTelemetryService);
    }

    @Test
    void dropsStatusWhenTopicAndPayloadRobotKeysDiffer() {
        handler()
                .messageArrived(
                        "hanbakwi/v1/robots/test-101/status",
                        mqttMessage(
                                """
                                {"schemaVersion":1,"robotKey":"robot17","battery":90.0,"state":"IDLE",
                                 "motor":"NORMAL","camera":"NORMAL","lidar":"NORMAL",
                                 "lineSensor":"DISCONNECTED","timestamp":"2026-08-04T12:00:00+09:00"}
                                """));

        verifyNoInteractions(robotTelemetryService);
    }

    @Test
    void routesTelemetryWhenTopicAndPayloadRobotKeysMatch() {
        MqttInboundHandler handler = handler();

        handler.messageArrived(
                "hanbakwi/v1/robots/test-101/pose",
                mqttMessage(
                        """
                        {"schemaVersion":1,"robotKey":"test-101","x":1.0,"y":2.0,
                         "heading":0.0,"timestamp":"2026-08-04T12:00:00+09:00"}
                        """));
        handler.messageArrived(
                "hanbakwi/v1/robots/test-101/status",
                mqttMessage(
                        """
                        {"schemaVersion":1,"robotKey":"test-101","battery":90.0,"state":"IDLE",
                         "motor":"NORMAL","camera":"NORMAL","lidar":"NORMAL",
                         "lineSensor":"DISCONNECTED","timestamp":"2026-08-04T12:00:00+09:00"}
                        """));

        verify(robotTelemetryService).updatePose(any(RobotPoseMessage.class));
        verify(robotTelemetryService).updateStatus(any(RobotStatusMessage.class));
    }

    @Test
    void routesOptionalFailureReason() {
        ArgumentCaptor<CommandAck> ackCaptor = ArgumentCaptor.forClass(CommandAck.class);

        handler()
                .messageArrived(
                        "hanbakwi/v1/robots/test-101/command/ack",
                        mqttMessage(
                                """
                                {"schemaVersion":1,"commandId":"command-1","command":"START_PATROL",
                                 "status":"REJECTED","receivedAt":"2026-08-04T12:00:00+09:00",
                                 "reason":"NAVIGATION_CONFIG_NOT_READY"}
                                """));

        verify(patrolCommandAckService).handle(eq("test-101"), ackCaptor.capture());
        assertThat(ackCaptor.getValue().reason()).isEqualTo("NAVIGATION_CONFIG_NOT_READY");
    }

    @Test
    void legacyAckWithoutReasonRemainsCompatible() {
        ArgumentCaptor<CommandAck> ackCaptor = ArgumentCaptor.forClass(CommandAck.class);

        handler()
                .messageArrived(
                        "hanbakwi/v1/robots/test-101/command/ack",
                        mqttMessage(
                                """
                                {"schemaVersion":1,"commandId":"command-1","command":"START_PATROL",
                                 "status":"SUCCEEDED","receivedAt":"2026-08-04T12:00:00+09:00"}
                                """));

        verify(patrolCommandAckService).handle(eq("test-101"), ackCaptor.capture());
        assertThat(ackCaptor.getValue().reason()).isNull();
    }

    @Test
    void routesStopMappingAckToMappingService() {
        ArgumentCaptor<CommandAck> ackCaptor = ArgumentCaptor.forClass(CommandAck.class);

        handler()
                .messageArrived(
                        "hanbakwi/v1/robots/test-101/command/ack",
                        mqttMessage(
                                """
                                {"schemaVersion":1,"commandId":"stop-command",
                                 "command":"STOP_MAPPING",
                                 "status":"SUCCEEDED","receivedAt":"2026-08-07T03:00:00Z"}
                                """));

        verify(mappingCommandAckService).handle(eq("test-101"), ackCaptor.capture());
        assertThat(ackCaptor.getValue().command()).isEqualTo("STOP_MAPPING");
    }

    private MqttInboundHandler handler() {
        return new MqttInboundHandler(
                client, robotTelemetryService, mappingCommandAckService, patrolCommandAckService);
    }

    private MqttMessage mqttMessage(String payload) {
        return new MqttMessage(payload.getBytes(StandardCharsets.UTF_8));
    }
}
