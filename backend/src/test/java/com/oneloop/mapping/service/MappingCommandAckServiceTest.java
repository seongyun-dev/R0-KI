package com.oneloop.mapping.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.domain.MappingStopCommandStatus;
import com.oneloop.mapping.event.MappingStatusChangedEvent;
import com.oneloop.mapping.event.MappingStopCommandStatusChangedEvent;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.robot.domain.PatrolRobot;
import java.time.OffsetDateTime;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class MappingCommandAckServiceTest {

    private static final String ROBOT_KEY = "mapping-robot";
    private static final String COMMAND_ID = "mapping-command";

    @Mock private MappingSessionRepository mappingSessionRepository;
    @Mock private ApplicationEventPublisher eventPublisher;
    @Mock private ApartmentComplex apartmentComplex;

    @ParameterizedTest
    @EnumSource(
            value = CommandAck.AckStatus.class,
            names = {"REJECTED", "FAILED"})
    void failedAckWhileMappingFailsSession(CommandAck.AckStatus ackStatus) {
        MappingSession session = createSession();
        session.startMapping();
        when(mappingSessionRepository.findByCommandId(COMMAND_ID))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(ROBOT_KEY, ack(ackStatus));

        assertThat(session.getStatus()).isEqualTo(MappingStatus.FAILED);
        assertThat(session.getFinishedAt()).isNotNull();
        ArgumentCaptor<MappingStatusChangedEvent> eventCaptor =
                ArgumentCaptor.forClass(MappingStatusChangedEvent.class);
        verify(eventPublisher).publishEvent(eventCaptor.capture());
        assertThat(eventCaptor.getValue().status()).isEqualTo(MappingStatus.FAILED);
    }

    @ParameterizedTest
    @EnumSource(
            value = MappingStatus.class,
            names = {"COMPLETED", "FAILED", "CANCELLED"})
    void failedAckDoesNotChangeTerminalSession(MappingStatus terminalStatus) {
        MappingSession session = createSession();
        ReflectionTestUtils.setField(session, "status", terminalStatus);
        when(mappingSessionRepository.findByCommandId(COMMAND_ID))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(ROBOT_KEY, ack(CommandAck.AckStatus.REJECTED));

        assertThat(session.getStatus()).isEqualTo(terminalStatus);
        verifyNoInteractions(eventPublisher);
    }

    @Test
    void successfulAckWhileMappingRemainsIdempotent() {
        MappingSession session = createSession();
        session.startMapping();
        when(mappingSessionRepository.findByCommandId(COMMAND_ID))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(ROBOT_KEY, ack(CommandAck.AckStatus.SUCCEEDED));

        assertThat(session.getStatus()).isEqualTo(MappingStatus.MAPPING);
        verifyNoInteractions(eventPublisher);
    }

    @Test
    void successfulStopAckDoesNotCompleteMappingSession() {
        MappingSession session = createSession();
        session.startMapping();
        session.prepareStop("stop-command");
        when(mappingSessionRepository.findByStopCommandId("stop-command"))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(ROBOT_KEY, stopAck("stop-command", CommandAck.AckStatus.SUCCEEDED));

        assertThat(session.getStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(session.getStopCommandStatus())
                .isEqualTo(MappingStopCommandStatus.ACK_SUCCEEDED);
        MappingStopCommandStatusChangedEvent event = captureStopEvent();
        assertThat(event.mappingStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(event.stopCommandStatus())
                .isEqualTo(MappingStopCommandStatus.ACK_SUCCEEDED);
        assertThat(event.reason()).isNull();
    }

    @ParameterizedTest
    @EnumSource(
            value = CommandAck.AckStatus.class,
            names = {"REJECTED", "FAILED"})
    void failedStopAckDoesNotFailActiveMapping(CommandAck.AckStatus ackStatus) {
        MappingSession session = createSession();
        session.startMapping();
        session.prepareStop("stop-command");
        when(mappingSessionRepository.findByStopCommandId("stop-command"))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(ROBOT_KEY, stopAck("stop-command", ackStatus));

        assertThat(session.getStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(session.getStopCommandStatus()).isEqualTo(MappingStopCommandStatus.FAILED);
        assertThat(session.getStopFailureReason()).isEqualTo("stop reason");
        MappingStopCommandStatusChangedEvent event = captureStopEvent();
        assertThat(event.mappingStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(event.stopCommandStatus()).isEqualTo(MappingStopCommandStatus.FAILED);
        assertThat(event.reason()).isEqualTo("stop reason");
    }

    @Test
    void duplicateStopAckDoesNotOverwriteFirstResult() {
        MappingSession session = createSession();
        session.startMapping();
        session.prepareStop("stop-command");
        when(mappingSessionRepository.findByStopCommandId("stop-command"))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(ROBOT_KEY, stopAck("stop-command", CommandAck.AckStatus.SUCCEEDED));
        service.handle(ROBOT_KEY, stopAck("stop-command", CommandAck.AckStatus.FAILED));

        assertThat(session.getStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(session.getStopCommandStatus())
                .isEqualTo(MappingStopCommandStatus.ACK_SUCCEEDED);
        verify(eventPublisher, times(1))
                .publishEvent(
                        org.mockito.ArgumentMatchers.any(
                                MappingStopCommandStatusChangedEvent.class));
    }

    @Test
    void stopAckFromAnotherRobotDoesNotPublishEvent() {
        MappingSession session = createSession();
        session.startMapping();
        session.prepareStop("stop-command");
        when(mappingSessionRepository.findByStopCommandId("stop-command"))
                .thenReturn(Optional.of(session));
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle("another-robot", stopAck("stop-command", CommandAck.AckStatus.FAILED));

        assertThat(session.getStopCommandStatus()).isEqualTo(MappingStopCommandStatus.PREPARED);
        verifyNoInteractions(eventPublisher);
    }

    @Test
    void stopAckWithUnknownCommandIdDoesNotPublishEvent() {
        when(mappingSessionRepository.findByStopCommandId("unknown-command"))
                .thenReturn(Optional.empty());
        MappingCommandAckService service =
                new MappingCommandAckService(mappingSessionRepository, eventPublisher);

        service.handle(
                ROBOT_KEY,
                stopAck("unknown-command", CommandAck.AckStatus.FAILED));

        verifyNoInteractions(eventPublisher);
    }

    private MappingStopCommandStatusChangedEvent captureStopEvent() {
        ArgumentCaptor<MappingStopCommandStatusChangedEvent> eventCaptor =
                ArgumentCaptor.forClass(MappingStopCommandStatusChangedEvent.class);
        verify(eventPublisher).publishEvent(eventCaptor.capture());
        return eventCaptor.getValue();
    }

    private MappingSession createSession() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "mapping-robot", ROBOT_KEY);
        return new MappingSession(apartmentComplex, robot, COMMAND_ID);
    }

    private CommandAck ack(CommandAck.AckStatus status) {
        return new CommandAck(
                1,
                COMMAND_ID,
                "START_MAPPING",
                status,
                OffsetDateTime.now());
    }

    private CommandAck stopAck(String commandId, CommandAck.AckStatus status) {
        return new CommandAck(
                1, commandId, "STOP_MAPPING", status, OffsetDateTime.now(), "stop reason");
    }
}
