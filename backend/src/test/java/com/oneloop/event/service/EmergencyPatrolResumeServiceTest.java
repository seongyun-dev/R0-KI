package com.oneloop.event.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventType;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.ResumePatrolCommand;
import com.oneloop.robot.domain.PatrolRobot;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;

@ExtendWith(MockitoExtension.class)
class EmergencyPatrolResumeServiceTest {

    @Mock private ObjectProvider<MqttPublisher> mqttPublisherProvider;
    @Mock private MqttPublisher mqttPublisher;
    @Mock private DetectedEvent event;
    @Mock private Patrol patrol;
    @Mock private PatrolRobot robot;

    @Test
    void completedEmergencyResumesOnlyItsActivePatrol() {
        when(event.getType()).thenReturn(EventType.EMERGENCY);
        when(event.getPatrol()).thenReturn(patrol);
        when(event.getRobot()).thenReturn(robot);
        when(patrol.getStatus()).thenReturn(PatrolStatus.IN_PROGRESS);
        when(patrol.getRobot()).thenReturn(robot);
        when(patrol.getId()).thenReturn(107L);
        when(robot.getId()).thenReturn(17L);
        when(robot.getSerialNumber()).thenReturn("test-101");
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);

        assertThat(service().resumeIfEligible(event)).isTrue();

        ArgumentCaptor<ResumePatrolCommand> command =
                ArgumentCaptor.forClass(ResumePatrolCommand.class);
        verify(mqttPublisher).publishCommand(org.mockito.ArgumentMatchers.eq("test-101"), command.capture());
        assertThat(command.getValue().command()).isEqualTo("RESUME_PATROL");
        assertThat(command.getValue().patrolId()).isEqualTo(107L);
        assertThat(command.getValue().expiresAt()).isAfter(command.getValue().issuedAt());
    }

    @Test
    void nonEmergencyEventNeverMovesRobot() {
        when(event.getType()).thenReturn(EventType.TRASH_DETECTED);

        assertThat(service().resumeIfEligible(event)).isFalse();

        verify(mqttPublisher, never()).publishCommand(any(), any());
    }

    @Test
    void endedPatrolEmergencyNeverMovesRobot() {
        when(event.getType()).thenReturn(EventType.EMERGENCY);
        when(event.getPatrol()).thenReturn(patrol);
        when(patrol.getStatus()).thenReturn(PatrolStatus.COMPLETED);

        assertThat(service().resumeIfEligible(event)).isFalse();

        verify(mqttPublisher, never()).publishCommand(any(), any());
    }

    private EmergencyPatrolResumeService service() {
        return new EmergencyPatrolResumeService(mqttPublisherProvider);
    }
}
