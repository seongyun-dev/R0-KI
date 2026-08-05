package com.oneloop.map.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.ZoneBatchCreateRequest;
import com.oneloop.map.dto.request.ZoneCreateRequest;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class ZoneServiceTest {

    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private CheckpointRepository checkpointRepository;
    @Mock private NavigationWaypointRepository navigationWaypointRepository;
    @Mock private NavigationConfigurationGuard navigationConfigurationGuard;
    @Mock private ApartmentComplex apartmentComplex;

    private ZoneService service;

    @BeforeEach
    void setUp() {
        PatrolMap patrolMap =
                new PatrolMap(
                        apartmentComplex,
                        "map",
                        "/api/map/files/map.png",
                        new BigDecimal("0.05"),
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        100,
                        100);
        ReflectionTestUtils.setField(patrolMap, "id", 31L);
        when(patrolMapRepository.findForUpdateByIdAndApartmentComplexId(31L, 2L))
                .thenReturn(Optional.of(patrolMap));
        service =
                new ZoneService(
                        patrolMapRepository,
                        checkpointRepository,
                        navigationWaypointRepository,
                        navigationConfigurationGuard);
    }

    @Test
    void replacesZonesAfterInvalidatingWaypointsAndOldActiveZones() {
        ZoneBatchCreateRequest request = request(1, zone("parking", "0", "0", "2", "2"));
        when(checkpointRepository.saveAll(anyList()))
                .thenAnswer(invocation -> invocation.getArgument(0));

        assertThat(service.createAll(2L, 31L, request)).hasSize(1);

        verify(patrolMapRepository).findForUpdateByIdAndApartmentComplexId(31L, 2L);
        verify(navigationConfigurationGuard).assertMutable(2L);
        InOrder order = inOrder(navigationWaypointRepository, checkpointRepository);
        order.verify(navigationWaypointRepository).deleteAllByPatrolMapId(31L);
        order.verify(checkpointRepository).deactivateAllByPatrolMapId(31L);
        order.verify(checkpointRepository).saveAll(anyList());
    }

    @Test
    void legacyRequestWithoutMapVersionStillUsesReplaceSemantics() {
        ZoneBatchCreateRequest request = request(null, zone("parking", "0", "0", "2", "2"));
        when(checkpointRepository.saveAll(anyList()))
                .thenAnswer(invocation -> invocation.getArgument(0));

        service.createAll(2L, 31L, request);

        verify(navigationWaypointRepository).deleteAllByPatrolMapId(31L);
        verify(checkpointRepository).deactivateAllByPatrolMapId(31L);
    }

    @Test
    void staleMapVersionDoesNotMutateConfiguration() {
        ZoneBatchCreateRequest request = request(2, zone("parking", "0", "0", "2", "2"));

        assertThatThrownBy(() -> service.createAll(2L, 31L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_VERSION_CONFLICT));
        verify(navigationConfigurationGuard, never()).assertMutable(2L);
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapId(31L);
        verify(checkpointRepository, never()).deactivateAllByPatrolMapId(31L);
    }

    @Test
    void invalidBoundsAreRejectedBeforeCurrentConfigurationIsTouched() {
        ZoneBatchCreateRequest request = request(1, zone("invalid", "1", "0", "1", "2"));

        assertThatThrownBy(() -> service.createAll(2L, 31L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.INVALID_ZONE_BOUNDS));
        verify(navigationConfigurationGuard, never()).assertMutable(2L);
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapId(31L);
        verify(checkpointRepository, never()).deactivateAllByPatrolMapId(31L);
    }

    @Test
    void activePatrolBlocksZoneReplacementBeforeInvalidation() {
        ZoneBatchCreateRequest request = request(1, zone("parking", "0", "0", "2", "2"));
        doThrow(new BusinessException(ErrorCode.MAP_CONFIGURATION_LOCKED))
                .when(navigationConfigurationGuard)
                .assertMutable(2L);

        assertThatThrownBy(() -> service.createAll(2L, 31L, request))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED));
        verify(navigationWaypointRepository, never()).deleteAllByPatrolMapId(31L);
        verify(checkpointRepository, never()).deactivateAllByPatrolMapId(31L);
    }

    private ZoneBatchCreateRequest request(Integer mapVersion, ZoneCreateRequest... zones) {
        ZoneBatchCreateRequest request = new ZoneBatchCreateRequest();
        request.setMapVersion(mapVersion);
        request.setZones(List.of(zones));
        return request;
    }

    private ZoneCreateRequest zone(
            String name, String startX, String startY, String endX, String endY) {
        ZoneCreateRequest request = new ZoneCreateRequest();
        request.setName(name);
        request.setType(CheckpointType.PARKING);
        request.setStartX(new BigDecimal(startX));
        request.setStartY(new BigDecimal(startY));
        request.setEndX(new BigDecimal(endX));
        request.setEndY(new BigDecimal(endY));
        return request;
    }
}
