package com.oneloop.map.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
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
import com.oneloop.map.dto.request.WaypointBatchReplaceRequest;
import com.oneloop.map.dto.request.WaypointReplaceItemRequest;
import com.oneloop.map.dto.response.WaypointSetResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
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
class NavigationWaypointServiceTest {

    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private CheckpointRepository checkpointRepository;
    @Mock private NavigationWaypointRepository navigationWaypointRepository;
    @Mock private NavigationConfigurationGuard navigationConfigurationGuard;
    @Mock private ApartmentComplex apartmentComplex;

    private PatrolMap patrolMap;
    private NavigationWaypointService service;

    @BeforeEach
    void setUp() {
        patrolMap = map(31L);
        service =
                new NavigationWaypointService(
                        patrolMapRepository,
                        checkpointRepository,
                        navigationWaypointRepository,
                        navigationConfigurationGuard);
        lenient()
                .when(patrolMapRepository.findByIdAndApartmentComplexId(31L, 2L))
                .thenReturn(Optional.of(patrolMap));
        lenient()
                .when(patrolMapRepository.findForUpdateByIdAndApartmentComplexId(31L, 2L))
                .thenReturn(Optional.of(patrolMap));
    }

    @Test
    void replacesOrderedRouteAndAppliesDefaultRadius() {
        Checkpoint parkingZone = zone(patrolMap, 91L, CheckpointType.PARKING);
        WaypointReplaceItemRequest destination =
                point(4, "3.5", "0.5", NavigationWaypointAction.DESTINATION, null);
        destination.setYaw(new BigDecimal("3.1416"));
        WaypointBatchReplaceRequest request =
                request(
                        point(1, "0.5", "0.5", NavigationWaypointAction.PASS, null),
                        point(2, "1.5", "0.5", NavigationWaypointAction.SCAN, 91L),
                        point(3, "2.5", "0.5", NavigationWaypointAction.SCAN, 91L),
                        destination);
        when(checkpointRepository.findAllActiveByPatrolMapIdAndIdIn(31L, List.of(91L)))
                .thenReturn(List.of(parkingZone));
        when(navigationWaypointRepository.saveAll(anyList()))
                .thenAnswer(invocation -> invocation.getArgument(0));

        WaypointSetResponse response = service.replaceAll(2L, 31L, request);

        assertThat(response.getMapId()).isEqualTo(31L);
        assertThat(response.getMapVersion()).isEqualTo(1);
        assertThat(response.getWaypoints())
                .extracting(item -> item.getSequence())
                .containsExactly(1, 2, 3, 4);
        assertThat(response.getWaypoints().get(1).getZoneId()).isEqualTo(91L);
        assertThat(response.getWaypoints().get(2).getZoneId()).isEqualTo(91L);
        assertThat(response.getWaypoints())
                .allSatisfy(
                        item ->
                                assertThat(item.getAcceptanceRadius())
                                        .isEqualByComparingTo("0.300"));
        assertThat(response.getWaypoints().get(3).getYaw()).isEqualByComparingTo("3.1416");
        verify(patrolMapRepository).findForUpdateByIdAndApartmentComplexId(31L, 2L);
        verify(navigationConfigurationGuard).assertMutable(2L);
        verify(navigationWaypointRepository).deleteAllByPatrolMapIdAndMapVersion(31L, 1);
    }

    @Test
    void acceptsNav2MinimumAcceptanceRadius() {
        WaypointReplaceItemRequest destination =
                point(1, "0.5", "0.5", NavigationWaypointAction.DESTINATION, null);
        destination.setAcceptanceRadius(new BigDecimal("0.20"));
        when(navigationWaypointRepository.saveAll(anyList()))
                .thenAnswer(invocation -> invocation.getArgument(0));

        WaypointSetResponse response = service.replaceAll(2L, 31L, request(destination));

        assertThat(response.getWaypoints())
                .singleElement()
                .extracting(item -> item.getAcceptanceRadius())
                .isEqualTo(new BigDecimal("0.200"));
    }

    @Test
    void rejectsAcceptanceRadiusBelowNav2GoalTolerance() {
        WaypointReplaceItemRequest destination =
                point(1, "0.5", "0.5", NavigationWaypointAction.DESTINATION, null);
        destination.setAcceptanceRadius(new BigDecimal("0.199"));

        assertInvalidRoute(request(destination));
    }

    @Test
    void readUsesNonLockingMapLookup() {
        when(navigationWaypointRepository.findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                        31L, 1))
                .thenReturn(List.of());

        service.findAll(2L, 31L);

        verify(patrolMapRepository).findByIdAndApartmentComplexId(31L, 2L);
        verify(patrolMapRepository, never()).findForUpdateByIdAndApartmentComplexId(31L, 2L);
    }

    @Test
    void rejectsNonContiguousSequenceBeforeReplacing() {
        assertInvalidRoute(
                request(
                        point(1, "0.5", "0.5", NavigationWaypointAction.PASS, null),
                        point(3, "2.0", "0.5", NavigationWaypointAction.DESTINATION, null)));
    }

    @Test
    void rejectsDestinationThatIsNotLast() {
        assertInvalidRoute(
                request(
                        point(1, "0.5", "0.5", NavigationWaypointAction.DESTINATION, null),
                        point(2, "2.0", "0.5", NavigationWaypointAction.PASS, null)));
    }

    @Test
    void rejectsPointOutsideRotatedMapBounds() {
        ReflectionTestUtils.setField(patrolMap, "originX", new BigDecimal("1.0"));
        ReflectionTestUtils.setField(patrolMap, "originY", new BigDecimal("2.0"));
        ReflectionTestUtils.setField(patrolMap, "originYaw", new BigDecimal("1.5708"));

        assertInvalidRoute(
                request(point(1, "0.5", "7.1", NavigationWaypointAction.DESTINATION, null)));
    }

    @Test
    void rejectsExactRightOrTopMapBoundary() {
        assertInvalidRoute(
                request(point(1, "5.0", "0.5", NavigationWaypointAction.DESTINATION, null)));
    }

    @Test
    void rejectsCoordinatesThatCannotBeStoredWithoutRounding() {
        assertInvalidRoute(
                request(point(1, "0.5004", "0.5", NavigationWaypointAction.DESTINATION, null)));
    }

    @Test
    void rejectsConsecutivePointsWhoseAcceptanceAreasOverlap() {
        assertInvalidRoute(
                request(
                        point(1, "0.5", "0.5", NavigationWaypointAction.PASS, null),
                        point(2, "1.0", "0.5", NavigationWaypointAction.DESTINATION, null)));
    }

    @Test
    void rejectsInactiveOrForeignZoneReference() {
        WaypointBatchReplaceRequest request =
                request(
                        point(1, "0.5", "0.5", NavigationWaypointAction.SCAN, 91L),
                        point(2, "2.0", "0.5", NavigationWaypointAction.DESTINATION, null));
        when(checkpointRepository.findAllActiveByPatrolMapIdAndIdIn(31L, List.of(91L)))
                .thenReturn(List.of());

        assertInvalidRoute(request);
    }

    @Test
    void rejectsStaleMapVersionWithoutReplacing() {
        WaypointBatchReplaceRequest request =
                request(point(1, "0.5", "0.5", NavigationWaypointAction.DESTINATION, null));
        request.setMapVersion(2);

        assertThatThrownBy(() -> service.replaceAll(2L, 31L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_VERSION_CONFLICT));
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapIdAndMapVersion(31L, 1);
    }

    @Test
    void archivedMapBlocksWaypointReplacement() {
        NavigationWaypointService guardedService =
                new NavigationWaypointService(
                        patrolMapRepository,
                        checkpointRepository,
                        navigationWaypointRepository,
                        new NavigationConfigurationGuard(null));
        PatrolMap archivedMap = map(32L);
        archivedMap.archive();
        when(patrolMapRepository.findForUpdateByIdAndApartmentComplexId(32L, 2L))
                .thenReturn(Optional.of(archivedMap));

        WaypointBatchReplaceRequest request =
                request(point(1, "0.5", "0.5", NavigationWaypointAction.DESTINATION, null));

        assertThatThrownBy(() -> guardedService.replaceAll(2L, 32L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_NOT_ACTIVE));
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapIdAndMapVersion(32L, 1);
    }

    @Test
    void activePatrolLocksConfigurationBeforeReplacing() {
        WaypointBatchReplaceRequest request =
                request(point(1, "0.5", "0.5", NavigationWaypointAction.DESTINATION, null));
        doThrow(new BusinessException(ErrorCode.MAP_CONFIGURATION_LOCKED))
                .when(navigationConfigurationGuard)
                .assertMutable(2L);

        assertThatThrownBy(() -> service.replaceAll(2L, 31L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED));
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapIdAndMapVersion(31L, 1);
    }

    @Test
    void storedRouteWithOverlappingAcceptanceAreasIsNotReady() {
        NavigationWaypoint first = waypoint(1, "0.5", NavigationWaypointAction.PASS, null);
        NavigationWaypoint destination =
                waypoint(2, "1.0", NavigationWaypointAction.DESTINATION, null);
        when(navigationWaypointRepository.findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                        31L, 1))
                .thenReturn(List.of(first, destination));

        assertThatThrownBy(() -> service.requireValidCurrentRoute(patrolMap))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.NAVIGATION_CONFIG_NOT_READY));
    }

    private void assertInvalidRoute(WaypointBatchReplaceRequest request) {
        assertThatThrownBy(() -> service.replaceAll(2L, 31L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.INVALID_WAYPOINT_ROUTE));
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapIdAndMapVersion(31L, 1);
    }

    private PatrolMap map(Long id) {
        PatrolMap map =
                new PatrolMap(
                        apartmentComplex,
                        "test-map",
                        "/api/map/files/test.png",
                        new BigDecimal("0.05"),
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        100,
                        100);
        ReflectionTestUtils.setField(map, "id", id);
        return map;
    }

    private Checkpoint zone(PatrolMap map, Long id, CheckpointType type) {
        Checkpoint zone =
                new Checkpoint(
                        map,
                        type,
                        "zone",
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ONE,
                        BigDecimal.ONE);
        ReflectionTestUtils.setField(zone, "id", id);
        return zone;
    }

    private NavigationWaypoint waypoint(
            int sequence, String x, NavigationWaypointAction action, Checkpoint zone) {
        return new NavigationWaypoint(
                patrolMap,
                1,
                sequence,
                new BigDecimal(x),
                new BigDecimal("0.5"),
                action,
                null,
                new BigDecimal("0.3"),
                zone);
    }

    private WaypointBatchReplaceRequest request(WaypointReplaceItemRequest... points) {
        return new WaypointBatchReplaceRequest(1, List.of(points));
    }

    private WaypointReplaceItemRequest point(
            int sequence, String x, String y, NavigationWaypointAction action, Long zoneId) {
        return new WaypointReplaceItemRequest(
                sequence, new BigDecimal(x), new BigDecimal(y), action, null, null, zoneId);
    }
}
