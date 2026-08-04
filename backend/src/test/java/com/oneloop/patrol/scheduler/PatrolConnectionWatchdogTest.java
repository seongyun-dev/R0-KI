package com.oneloop.patrol.scheduler;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class PatrolConnectionWatchdogTest {

    @Mock private PatrolRepository patrolRepository;
    @Mock private ApplicationEventPublisher eventPublisher;
    @Mock private ApartmentComplex apartmentComplex;

    @Test
    void staleConnectionFailsPatrolAndMarksRobotOffline() {
        LocalDateTime staleTime = LocalDateTime.now().minusMinutes(1);
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "R-01", "robot-key");
        robot.updateStatus(
                RobotStatus.PATROLLING,
                new BigDecimal("80"),
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                staleTime,
                null,
                null);
        Patrol patrol = new Patrol(robot, staleTime.minusMinutes(5), "command");
        when(patrolRepository.findAllByStatusIn(
                        List.of(PatrolStatus.IN_PROGRESS, PatrolStatus.STOP_REQUESTED)))
                .thenReturn(List.of(patrol));
        PatrolConnectionWatchdog watchdog =
                new PatrolConnectionWatchdog(patrolRepository, eventPublisher);
        ReflectionTestUtils.setField(watchdog, "connectionTimeoutSeconds", 15L);

        watchdog.failDisconnectedPatrols();

        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.FAILED);
        assertThat(patrol.getEndedAt()).isNotNull();
        assertThat(robot.getStatus()).isEqualTo(RobotStatus.OFFLINE);
    }
}
