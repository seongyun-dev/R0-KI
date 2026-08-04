package com.oneloop.robot.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.patrol.repository.RoutePositionRepository;
import com.oneloop.patrol.service.PatrolCommandService;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import com.oneloop.robot.dto.mqtt.RobotPoseMessage;
import com.oneloop.robot.dto.mqtt.RobotStatusMessage;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

@ExtendWith(MockitoExtension.class)
class RobotTelemetryServiceTest {

    @Mock private RobotRepository robotRepository;
    @Mock private PatrolRepository patrolRepository;
    @Mock private RoutePositionRepository routePositionRepository;
    @Mock private ApplicationEventPublisher eventPublisher;
    @Mock private PatrolCommandService patrolCommandService;
    @Mock private ApartmentComplex apartmentComplex;

    @Test
    void statusConnectionFreshnessUsesServerReceiptTimeInsteadOfPayloadTime() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "demo-robot", "test-101");
        OffsetDateTime payloadTime = OffsetDateTime.now().minusHours(6);
        when(robotRepository.findBySerialNumber("test-101")).thenReturn(Optional.of(robot));
        when(apartmentComplex.getId()).thenReturn(2L);
        LocalDateTime beforeReceipt = LocalDateTime.now().minusSeconds(1);

        service()
                .updateStatus(
                        new RobotStatusMessage(
                                1,
                                "test-101",
                                new BigDecimal("80"),
                                RobotStatus.IDLE,
                                SensorStatus.NORMAL,
                                SensorStatus.NORMAL,
                                SensorStatus.NORMAL,
                                SensorStatus.DISCONNECTED,
                                null,
                                payloadTime));

        assertThat(robot.getStatusReportedAt()).isEqualTo(payloadTime.toLocalDateTime());
        assertThat(robot.getLastConnectedAt())
                .isBetween(beforeReceipt, LocalDateTime.now().plusSeconds(1));
    }

    @Test
    void poseDoesNotRefreshStatusHeartbeatConnectionTime() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "demo-robot", "test-101");
        OffsetDateTime payloadTime = OffsetDateTime.now().plusHours(6);
        LocalDateTime previousStatusReceipt = LocalDateTime.now().minusMinutes(1);
        robot.recordConnection(previousStatusReceipt);
        when(robotRepository.findBySerialNumber("test-101")).thenReturn(Optional.of(robot));
        when(apartmentComplex.getId()).thenReturn(2L);

        service()
                .updatePose(
                        new RobotPoseMessage(
                                1,
                                "test-101",
                                new BigDecimal("1.6"),
                                new BigDecimal("2.5"),
                                BigDecimal.ZERO,
                                payloadTime));

        assertThat(robot.getLocationUpdatedAt()).isEqualTo(payloadTime.toLocalDateTime());
        assertThat(robot.getLastConnectedAt()).isEqualTo(previousStatusReceipt);
    }

    private RobotTelemetryService service() {
        return new RobotTelemetryService(
                robotRepository,
                patrolRepository,
                routePositionRepository,
                eventPublisher,
                patrolCommandService);
    }
}
