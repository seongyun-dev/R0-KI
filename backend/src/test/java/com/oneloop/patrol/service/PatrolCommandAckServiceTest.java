package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PatrolCommandAckServiceTest {

    @Mock private PatrolRepository patrolRepository;
    @Mock private PatrolAiSummaryService patrolAiSummaryService;
    @Mock private ApartmentComplex apartmentComplex;

    @Test
    void successfulStopAckFinalizesRequestedPatrol() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "R-01", "robot-key");
        Patrol patrol = new Patrol(robot, LocalDateTime.now().minusMinutes(3), "start-command");
        patrol.requestStop("stop-command");
        when(patrolRepository.findByCommandId("stop-command")).thenReturn(Optional.of(patrol));
        PatrolCommandAckService service =
                new PatrolCommandAckService(patrolRepository, patrolAiSummaryService);

        service.handle(
                "robot-key",
                new CommandAck(
                        1,
                        "stop-command",
                        "STOP_PATROL",
                        CommandAck.AckStatus.SUCCEEDED,
                        OffsetDateTime.now()));

        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.STOPPED);
        assertThat(patrol.getEndedAt()).isNotNull();
        assertThat(patrol.getTotalDuration()).isGreaterThanOrEqualTo(0);
        verify(patrolAiSummaryService, never()).requestGeneration(patrol.getId());
    }

    @Test
    void successfulAutomaticStopAckCompletesAndRequestsSummary() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "R-01", "robot-key");
        Patrol patrol = new Patrol(robot, LocalDateTime.now().minusMinutes(3), "start-command");
        patrol.requestCompletion("stop-command");
        when(patrolRepository.findByCommandId("stop-command")).thenReturn(Optional.of(patrol));
        PatrolCommandAckService service =
                new PatrolCommandAckService(patrolRepository, patrolAiSummaryService);

        service.handle(
                "robot-key",
                new CommandAck(
                        1,
                        "stop-command",
                        "STOP_PATROL",
                        CommandAck.AckStatus.SUCCEEDED,
                        OffsetDateTime.now()));

        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.COMPLETED);
        assertThat(patrol.isCompletionRequested()).isFalse();
        verify(patrolAiSummaryService).requestGeneration(patrol.getId());
    }

    @Test
    void failedAutomaticStopAckReturnsToRetryableInProgressState() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "R-01", "robot-key");
        Patrol patrol = new Patrol(robot, LocalDateTime.now().minusMinutes(3), "start-command");
        patrol.requestCompletion("stop-command");
        when(patrolRepository.findByCommandId("stop-command")).thenReturn(Optional.of(patrol));
        PatrolCommandAckService service =
                new PatrolCommandAckService(patrolRepository, patrolAiSummaryService);

        service.handle(
                "robot-key",
                new CommandAck(
                        1,
                        "stop-command",
                        "STOP_PATROL",
                        CommandAck.AckStatus.FAILED,
                        OffsetDateTime.now(),
                        "STOP_NOT_CONFIRMED"));

        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.IN_PROGRESS);
        assertThat(patrol.isCompletionRequested()).isFalse();
        verify(patrolAiSummaryService, never()).requestGeneration(patrol.getId());
    }
}
