package com.oneloop.map.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.response.NavigationConfigResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class RobotNavigationConfigServiceTest {

    @Mock private RobotRepository robotRepository;
    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private CheckpointRepository checkpointRepository;
    @Mock private NavigationWaypointService navigationWaypointService;

    private ApartmentComplex apartmentComplex;
    private PatrolMap patrolMap;
    private PatrolRobot robot;
    private RobotNavigationConfigService service;

    @BeforeEach
    void setUp() {
        apartmentComplex = new ApartmentComplex("complex", "address", "00000");
        ReflectionTestUtils.setField(apartmentComplex, "id", 2L);
        patrolMap =
                new PatrolMap(
                        apartmentComplex,
                        "map",
                        "/api/map/files/map.png",
                        new BigDecimal("0.05"),
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        100,
                        80);
        ReflectionTestUtils.setField(patrolMap, "id", 31L);
        robot = new PatrolRobot(apartmentComplex, "robot", "test-101");
        ReflectionTestUtils.setField(robot, "id", 17L);
        service =
                new RobotNavigationConfigService(
                        robotRepository,
                        patrolMapRepository,
                        checkpointRepository,
                        navigationWaypointService);
    }

    @Test
    void returnsCurrentMapZonesAndOrderedWaypointsForAuthenticatedRobot() {
        Checkpoint parking =
                new Checkpoint(
                        patrolMap,
                        CheckpointType.PARKING,
                        "parking",
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ONE,
                        BigDecimal.ONE);
        ReflectionTestUtils.setField(parking, "id", 91L);
        NavigationWaypoint scan = waypoint(1, "1.0", NavigationWaypointAction.SCAN, parking);
        NavigationWaypoint destination =
                waypoint(2, "2.0", NavigationWaypointAction.DESTINATION, null);
        when(robotRepository.findByIdAndStatusNot(17L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolMapRepository.findByApartmentComplexId(2L)).thenReturn(Optional.of(patrolMap));
        when(navigationWaypointService.requireValidCurrentRoute(patrolMap))
                .thenReturn(List.of(scan, destination));
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(parking));

        NavigationConfigResponse response = service.get(17L);

        assertThat(response.getSchemaVersion()).isEqualTo(1);
        assertThat(response.getMap().getMapId()).isEqualTo(31L);
        assertThat(response.getMap().getMapVersion()).isEqualTo(1);
        assertThat(response.getMap().getOriginYaw()).isEqualByComparingTo("0");
        assertThat(response.getZones())
                .singleElement()
                .extracting(item -> item.getZoneId())
                .isEqualTo(91L);
        assertThat(response.getWaypoints())
                .extracting(item -> item.getSequence())
                .containsExactly(1, 2);
        assertThat(response.getWaypoints().get(0).getZoneId()).isEqualTo(91L);
        verify(patrolMapRepository).findByApartmentComplexId(2L);
    }

    @Test
    void missingMapIsReportedAsNavigationConfigNotReady() {
        when(robotRepository.findByIdAndStatusNot(17L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolMapRepository.findByApartmentComplexId(2L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get(17L))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.NAVIGATION_CONFIG_NOT_READY));
    }

    @Test
    void unknownOrDeletedRobotCannotReadAnotherApartmentConfiguration() {
        when(robotRepository.findByIdAndStatusNot(17L, RobotStatus.DELETED))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get(17L))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.ROBOT_NOT_FOUND));
    }

    private NavigationWaypoint waypoint(
            int sequence, String x, NavigationWaypointAction action, Checkpoint zone) {
        NavigationWaypoint waypoint =
                new NavigationWaypoint(
                        patrolMap,
                        1,
                        sequence,
                        new BigDecimal(x),
                        new BigDecimal("0.5"),
                        action,
                        null,
                        new BigDecimal("0.3"),
                        zone);
        ReflectionTestUtils.setField(waypoint, "id", 100L + sequence);
        return waypoint;
    }
}
