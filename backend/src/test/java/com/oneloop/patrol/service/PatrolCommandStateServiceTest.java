package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.service.NavigationWaypointService;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class PatrolCommandStateServiceTest {

    @Mock private PatrolRepository patrolRepository;
    @Mock private RobotRepository robotRepository;
    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private NavigationWaypointService navigationWaypointService;

    private PatrolCommandStateService service;
    private PatrolRobot robot;
    private PatrolMap patrolMap;

    @BeforeEach
    void setUp() {
        ApartmentComplex apartment = new ApartmentComplex("complex", "address", "00000");
        ReflectionTestUtils.setField(apartment, "id", 2L);
        robot = new PatrolRobot(apartment, "robot", "test-101");
        ReflectionTestUtils.setField(robot, "id", 17L);
        patrolMap =
                new PatrolMap(
                        apartment,
                        "map",
                        "/api/map/files/map.png",
                        new BigDecimal("0.05"),
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        100,
                        100);
        ReflectionTestUtils.setField(patrolMap, "id", 31L);
        service =
                new PatrolCommandStateService(
                        patrolRepository,
                        robotRepository,
                        patrolMapRepository,
                        navigationWaypointService);
    }

    @Test
    void requestsStopOnlyAtDestinationAndRepeatedPoseReusesCommand() {
        Patrol patrol = patrol();
        NavigationWaypoint pass = waypoint(1, "0.5", NavigationWaypointAction.PASS);
        NavigationWaypoint destination = waypoint(2, "2.0", NavigationWaypointAction.DESTINATION);
        when(patrolRepository.findFirstForUpdateByRobotIdOrderByStartedAtDesc(17L))
                .thenReturn(Optional.of(patrol));
        when(patrolMapRepository.findByApartmentComplexId(2L)).thenReturn(Optional.of(patrolMap));
        when(navigationWaypointService.requireValidCurrentRoute(patrolMap))
                .thenReturn(List.of(pass, destination));

        assertThat(service.prepareAutoComplete(17L, new BigDecimal("0.5"), new BigDecimal("0.5")))
                .isEmpty();
        PatrolCommandStateService.PreparedAutoComplete first =
                service.prepareAutoComplete(17L, new BigDecimal("2.3"), new BigDecimal("0.5"))
                        .orElseThrow();
        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.STOP_REQUESTED);
        assertThat(patrol.isCompletionRequested()).isTrue();
        PatrolCommandStateService.PreparedAutoComplete retry =
                service.prepareAutoComplete(17L, new BigDecimal("2.0"), new BigDecimal("0.5"))
                        .orElseThrow();
        assertThat(retry.commandId()).isEqualTo(first.commandId());
        verify(navigationWaypointService, times(2)).requireValidCurrentRoute(patrolMap);
    }

    @Test
    void poseOutsideAcceptanceRadiusDoesNotCompletePatrol() {
        Patrol patrol = patrol();
        NavigationWaypoint destination = waypoint(1, "2.0", NavigationWaypointAction.DESTINATION);
        when(patrolRepository.findFirstForUpdateByRobotIdOrderByStartedAtDesc(17L))
                .thenReturn(Optional.of(patrol));
        when(patrolMapRepository.findByApartmentComplexId(2L)).thenReturn(Optional.of(patrolMap));
        when(navigationWaypointService.requireValidCurrentRoute(patrolMap))
                .thenReturn(List.of(destination));

        assertThat(service.prepareAutoComplete(17L, new BigDecimal("2.301"), new BigDecimal("0.5")))
                .isEmpty();
        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.IN_PROGRESS);
    }

    private Patrol patrol() {
        Patrol patrol =
                new Patrol(
                        robot, LocalDateTime.now().minusMinutes(1), UUID.randomUUID().toString());
        ReflectionTestUtils.setField(patrol, "id", 29L);
        return patrol;
    }

    private NavigationWaypoint waypoint(int sequence, String x, NavigationWaypointAction action) {
        return new NavigationWaypoint(
                patrolMap,
                patrolMap.getMapVersion(),
                sequence,
                new BigDecimal(x),
                new BigDecimal("0.5"),
                action,
                null,
                new BigDecimal("0.3"),
                null);
    }
}
