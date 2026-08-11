package com.oneloop.map.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.file.FileStorageProperties;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.MapStatus;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.MapUploadRequest;
import com.oneloop.map.dto.request.WaypointBatchReplaceRequest;
import com.oneloop.map.dto.request.WaypointReplaceItemRequest;
import com.oneloop.map.dto.request.ZoneBatchCreateRequest;
import com.oneloop.map.dto.request.ZoneCreateRequest;
import com.oneloop.map.dto.response.MapDetailResponse;
import com.oneloop.map.dto.response.MapListResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.repository.RobotRepository;
import jakarta.persistence.EntityManager;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.multipart.MultipartFile;

@ActiveProfiles("test")
@SpringBootTest
@Import(MapConfigurationTransactionIntegrationTest.TestConfig.class)
class MapConfigurationTransactionIntegrationTest {

    @Autowired private ApartmentComplexRepository apartmentComplexRepository;
    @Autowired private RobotRepository robotRepository;
    @Autowired private PatrolMapRepository patrolMapRepository;
    @Autowired private CheckpointRepository checkpointRepository;
    @Autowired private NavigationWaypointRepository navigationWaypointRepository;
    @Autowired private PatrolRepository patrolRepository;
    @Autowired private PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;
    @Autowired private MappingSessionRepository mappingSessionRepository;
    @Autowired private ZoneService zoneService;
    @Autowired private MapService mapService;
    @Autowired private NavigationWaypointService navigationWaypointService;
    @Autowired private FakeMapFileStorage fakeMapFileStorage;
    @Autowired private EntityManager entityManager;

    @Test
    void zoneReplacePreservesHistoricalCheckpointVisitAndRemovesCurrentRoute() {
        Fixture fixture = fixture("zone-replace");
        Checkpoint oldZone = checkpoint(fixture.map(), "old parking");
        Patrol patrol =
                new Patrol(
                        fixture.robot(),
                        LocalDateTime.now().minusMinutes(1),
                        UUID.randomUUID().toString());
        patrol.complete();
        patrol = patrolRepository.saveAndFlush(patrol);
        PatrolCheckpointVisit visit =
                patrolCheckpointVisitRepository.saveAndFlush(
                        new PatrolCheckpointVisit(patrol, oldZone, 1, LocalDateTime.now()));
        navigationWaypointRepository.saveAndFlush(
                waypoint(
                        fixture.map(),
                        fixture.map().getMapVersion(),
                        1,
                        NavigationWaypointAction.DESTINATION,
                        oldZone));

        zoneService.createAll(
                fixture.apartment().getId(),
                fixture.map().getId(),
                zoneRequest(fixture.map().getMapVersion(), "new parking"));

        assertThat(patrolCheckpointVisitRepository.existsById(visit.getId())).isTrue();
        assertThat(checkpointRepository.findById(oldZone.getId()))
                .get()
                .extracting(Checkpoint::isActive)
                .isEqualTo(false);
        assertThat(checkpointRepository.findAllByPatrolMapId(fixture.map().getId()))
                .singleElement()
                .extracting(Checkpoint::getName)
                .isEqualTo("new parking");
        assertThat(
                        navigationWaypointRepository
                                .findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                                        fixture.map().getId(), fixture.map().getMapVersion()))
                .isEmpty();
    }

    @Test
    void failedZoneInsertRollsBackDeactivationAndRouteDeletion() {
        Fixture fixture = fixture("zone-rollback");
        Checkpoint oldZone = checkpoint(fixture.map(), "old parking");
        NavigationWaypoint route =
                navigationWaypointRepository.saveAndFlush(
                        waypoint(
                                fixture.map(),
                                fixture.map().getMapVersion(),
                                1,
                                NavigationWaypointAction.DESTINATION,
                                oldZone));
        ZoneBatchCreateRequest request =
                zoneRequest(fixture.map().getMapVersion(), "x".repeat(101));

        assertThatThrownBy(
                        () ->
                                zoneService.createAll(
                                        fixture.apartment().getId(),
                                        fixture.map().getId(),
                                        request))
                .isInstanceOf(RuntimeException.class);

        assertThat(checkpointRepository.findById(oldZone.getId()))
                .get()
                .extracting(Checkpoint::isActive)
                .isEqualTo(true);
        assertThat(navigationWaypointRepository.findById(route.getId())).isPresent();
    }

    @Test
    void mapReuploadInsertsNewActiveMapAndKeepsPreviousConfiguration() {
        Fixture fixture = fixture("map-reupload");
        Checkpoint oldZone = checkpoint(fixture.map(), "old parking");
        navigationWaypointRepository.saveAndFlush(
                waypoint(
                        fixture.map(),
                        fixture.map().getMapVersion(),
                        1,
                        NavigationWaypointAction.DESTINATION,
                        oldZone));
        String commandId = UUID.randomUUID().toString();
        MappingSession session =
                new MappingSession(fixture.apartment(), fixture.robot(), commandId);
        session.startMapping();
        mappingSessionRepository.saveAndFlush(session);

        MapUploadRequest request = uploadRequest(commandId);
        var uploadResponse =
                mapService.upload(session.getId(), fixture.robot().getId(), request);

        assertThat(mappingSessionRepository.findById(session.getId()))
                .get()
                .extracting(MappingSession::getStatus)
                .isEqualTo(MappingStatus.COMPLETED);

        PatrolMap archivedMap = patrolMapRepository.findById(fixture.map().getId()).orElseThrow();
        assertThat(archivedMap.getMapVersion()).isEqualTo(1);
        assertThat(archivedMap.getStatus()).isEqualTo(MapStatus.ARCHIVED);
        assertThat(checkpointRepository.findAllByPatrolMapId(archivedMap.getId()))
                .extracting(Checkpoint::getName)
                .containsExactly("old parking");
        assertThat(
                        navigationWaypointRepository
                                .findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                                        archivedMap.getId(), archivedMap.getMapVersion()))
                .hasSize(1);

        PatrolMap newMap = patrolMapRepository.findById(uploadResponse.getMapId()).orElseThrow();
        assertThat(newMap.getId()).isNotEqualTo(archivedMap.getId());
        assertThat(newMap.getStatus()).isEqualTo(MapStatus.ACTIVE);
        assertThat(newMap.getMapVersion()).isEqualTo(1);
        assertThat(checkpointRepository.findAllByPatrolMapId(newMap.getId())).isEmpty();
        assertThat(apartmentComplexRepository.findById(fixture.apartment().getId()))
                .get()
                .extracting(apartment -> apartment.getActiveMap().getId())
                .isEqualTo(newMap.getId());

        mapService.upload(session.getId(), fixture.robot().getId(), request);

        assertThat(patrolMapRepository.findById(newMap.getId()).orElseThrow().getMapVersion())
                .isEqualTo(1);
        assertThat(mapService.getCurrent(fixture.apartment().getId()).getMapId())
                .isEqualTo(newMap.getId());
        assertThat(fakeMapFileStorage.storeCount()).isEqualTo(1);
    }

    @Test
    void listActivateAndDeleteFollowMultiMapLifecycle() {
        Fixture fixture = fixture("map-lifecycle");
        String commandId = UUID.randomUUID().toString();
        MappingSession session =
                new MappingSession(fixture.apartment(), fixture.robot(), commandId);
        session.startMapping();
        mappingSessionRepository.saveAndFlush(session);

        var uploadResponse =
                mapService.upload(
                        session.getId(), fixture.robot().getId(), uploadRequest(commandId));
        PatrolMap first = fixture.map();
        PatrolMap second =
                patrolMapRepository.findById(uploadResponse.getMapId()).orElseThrow();

        MapListResponse listed = mapService.list(fixture.apartment().getId());
        assertThat(listed.getActiveMapId()).isEqualTo(second.getId());
        assertThat(listed.getMaps())
                .extracting(MapDetailResponse::getMapId)
                .containsExactly(second.getId(), first.getId());
        assertThat(listed.getMaps().get(0).getStatus()).isEqualTo(MapStatus.ACTIVE);

        MapDetailResponse activated =
                mapService.activate(fixture.apartment().getId(), first.getId());
        assertThat(activated.getMapId()).isEqualTo(first.getId());
        assertThat(activated.getStatus()).isEqualTo(MapStatus.ACTIVE);
        assertThat(patrolMapRepository.findById(second.getId()).orElseThrow().getStatus())
                .isEqualTo(MapStatus.ARCHIVED);
        assertThat(mapService.activate(fixture.apartment().getId(), first.getId()).getMapId())
                .isEqualTo(first.getId());

        assertThatThrownBy(
                        () -> mapService.delete(fixture.apartment().getId(), first.getId()))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getErrorCode())
                .isEqualTo(ErrorCode.MAP_ACTIVE_CANNOT_DELETE);

        Patrol patrol =
                patrolRepository.saveAndFlush(
                        new Patrol(
                                fixture.robot(),
                                second,
                                LocalDateTime.now(),
                                UUID.randomUUID().toString()));
        assertThatThrownBy(
                        () -> mapService.delete(fixture.apartment().getId(), second.getId()))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getErrorCode())
                .isEqualTo(ErrorCode.MAP_REFERENCED_BY_PATROL);

        patrolRepository.delete(patrol);

        mapService.delete(fixture.apartment().getId(), second.getId());
        assertThat(patrolMapRepository.findById(second.getId())).isEmpty();
    }

    @Test
    void archivedMapAllowsReadButBlocksEditUntilActivated() {
        Fixture fixture = fixture("archived-edit-guard");
        Checkpoint zone = checkpoint(fixture.map(), "archived parking");
        navigationWaypointRepository.saveAndFlush(
                waypoint(
                        fixture.map(),
                        fixture.map().getMapVersion(),
                        1,
                        NavigationWaypointAction.DESTINATION,
                        zone));

        String commandId = UUID.randomUUID().toString();
        MappingSession session =
                new MappingSession(fixture.apartment(), fixture.robot(), commandId);
        session.startMapping();
        mappingSessionRepository.saveAndFlush(session);
        mapService.upload(session.getId(), fixture.robot().getId(), uploadRequest(commandId));

        PatrolMap archived = fixture.map();
        PatrolMap active =
                patrolMapRepository
                        .findByApartmentComplexId(fixture.apartment().getId())
                        .orElseThrow();

        assertThat(zoneService.findAll(fixture.apartment().getId(), archived.getId())).hasSize(1);
        assertThat(
                        navigationWaypointService
                                .findAll(fixture.apartment().getId(), archived.getId())
                                .getWaypoints())
                .hasSize(1);

        assertThatThrownBy(
                        () ->
                                zoneService.createAll(
                                        fixture.apartment().getId(),
                                        archived.getId(),
                                        zoneRequest(archived.getMapVersion(), "new parking")))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_NOT_ACTIVE));

        mapService.activate(fixture.apartment().getId(), archived.getId());
        zoneService.createAll(
                fixture.apartment().getId(),
                archived.getId(),
                zoneRequest(archived.getMapVersion(), "new parking"));
        assertThat(checkpointRepository.findAllByPatrolMapId(archived.getId()))
                .extracting(Checkpoint::getName)
                .containsExactly("new parking");
        assertThat(
                        patrolMapRepository
                                .findByApartmentComplexId(fixture.apartment().getId())
                                .map(PatrolMap::getId))
                .contains(archived.getId());
        assertThat(active.getId()).isNotEqualTo(archived.getId());
    }

    @Test
    void activePatrolBlocksConfigurationReplacement() {
        Fixture fixture = fixture("active-patrol");
        Checkpoint oldZone = checkpoint(fixture.map(), "old parking");
        navigationWaypointRepository.saveAndFlush(
                waypoint(
                        fixture.map(),
                        fixture.map().getMapVersion(),
                        1,
                        NavigationWaypointAction.DESTINATION,
                        oldZone));
        patrolRepository.saveAndFlush(
                new Patrol(fixture.robot(), LocalDateTime.now(), UUID.randomUUID().toString()));

        assertThatThrownBy(
                        () ->
                                zoneService.createAll(
                                        fixture.apartment().getId(),
                                        fixture.map().getId(),
                                        zoneRequest(fixture.map().getMapVersion(), "new parking")))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED));

        WaypointBatchReplaceRequest waypointRequest =
                new WaypointBatchReplaceRequest(
                        fixture.map().getMapVersion(),
                        List.of(
                                waypointRequest(
                                        1, "0.5", "0.5", NavigationWaypointAction.DESTINATION)));
        assertThatThrownBy(
                        () ->
                                navigationWaypointService.replaceAll(
                                        fixture.apartment().getId(),
                                        fixture.map().getId(),
                                        waypointRequest))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED));

        String commandId = UUID.randomUUID().toString();
        MappingSession mappingSession =
                new MappingSession(fixture.apartment(), fixture.robot(), commandId);
        mappingSession.startMapping();
        mappingSessionRepository.saveAndFlush(mappingSession);
        int storeCountBefore = fakeMapFileStorage.storeCount();
        assertThatThrownBy(
                        () ->
                                mapService.upload(
                                        mappingSession.getId(),
                                        fixture.robot().getId(),
                                        uploadRequest(commandId)))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED));
        assertThat(fakeMapFileStorage.storeCount()).isEqualTo(storeCountBefore);

        assertThat(checkpointRepository.findById(oldZone.getId()))
                .get()
                .extracting(Checkpoint::isActive)
                .isEqualTo(true);
        assertThat(
                        navigationWaypointRepository
                                .findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                                        fixture.map().getId(), fixture.map().getMapVersion()))
                .hasSize(1);
    }

    @Test
    void savedWaypointPrecisionRemainsValidAfterReload() {
        Fixture fixture = fixture("waypoint-roundtrip");
        WaypointBatchReplaceRequest request =
                new WaypointBatchReplaceRequest(
                        fixture.map().getMapVersion(),
                        List.of(
                                waypointRequest(
                                        1, "0.5000", "0.5000", NavigationWaypointAction.PASS),
                                waypointRequest(
                                        2,
                                        "1.1010",
                                        "0.5000",
                                        NavigationWaypointAction.DESTINATION)));

        navigationWaypointService.replaceAll(
                fixture.apartment().getId(), fixture.map().getId(), request);
        entityManager.clear();
        PatrolMap reloaded = patrolMapRepository.findById(fixture.map().getId()).orElseThrow();

        assertThat(navigationWaypointService.requireValidCurrentRoute(reloaded))
                .extracting(NavigationWaypoint::getX)
                .containsExactly(new BigDecimal("0.500"), new BigDecimal("1.101"));
    }

    @Test
    void databaseRejectsAcceptanceRadiusBelowNav2GoalTolerance() {
        Fixture fixture = fixture("waypoint-radius-constraint");
        Checkpoint zone = checkpoint(fixture.map(), "parking");
        NavigationWaypoint invalid =
                new NavigationWaypoint(
                        fixture.map(),
                        fixture.map().getMapVersion(),
                        1,
                        new BigDecimal("0.5"),
                        new BigDecimal("0.5"),
                        NavigationWaypointAction.DESTINATION,
                        null,
                        new BigDecimal("0.199"),
                        zone);

        assertThatThrownBy(() -> navigationWaypointRepository.saveAndFlush(invalid))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    private Fixture fixture(String prefix) {
        String unique = prefix + "-" + UUID.randomUUID();
        ApartmentComplex apartment =
                apartmentComplexRepository.saveAndFlush(
                        new ApartmentComplex(unique, "integration-address", "00000"));
        PatrolRobot robot =
                robotRepository.saveAndFlush(new PatrolRobot(apartment, "robot", unique));
        PatrolMap map =
                patrolMapRepository.saveAndFlush(
                        new PatrolMap(
                                apartment,
                                "map",
                                "/api/map/files/old.png",
                                new BigDecimal("0.05"),
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                100,
                                100));
        apartment.assignActiveMap(map);
        apartmentComplexRepository.saveAndFlush(apartment);
        return new Fixture(apartment, robot, map);
    }

    private Checkpoint checkpoint(PatrolMap map, String name) {
        return checkpointRepository.saveAndFlush(
                new Checkpoint(
                        map,
                        CheckpointType.PARKING,
                        name,
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ONE,
                        BigDecimal.ONE));
    }

    private NavigationWaypoint waypoint(
            PatrolMap map,
            int mapVersion,
            int sequence,
            NavigationWaypointAction action,
            Checkpoint zone) {
        return new NavigationWaypoint(
                map,
                mapVersion,
                sequence,
                new BigDecimal("0.5"),
                new BigDecimal("0.5"),
                action,
                null,
                new BigDecimal("0.3"),
                zone);
    }

    private WaypointReplaceItemRequest waypointRequest(
            int sequence, String x, String y, NavigationWaypointAction action) {
        return new WaypointReplaceItemRequest(
                sequence, new BigDecimal(x), new BigDecimal(y), action, null, null, null);
    }

    private ZoneBatchCreateRequest zoneRequest(Integer mapVersion, String name) {
        ZoneBatchCreateRequest request = new ZoneBatchCreateRequest();
        request.setMapVersion(mapVersion);
        request.setZones(List.of(zoneRequest(name)));
        return request;
    }

    private ZoneCreateRequest zoneRequest(String name) {
        ZoneCreateRequest request = new ZoneCreateRequest();
        request.setName(name);
        request.setType(CheckpointType.PARKING);
        request.setStartX(BigDecimal.ZERO);
        request.setStartY(BigDecimal.ZERO);
        request.setEndX(new BigDecimal("2"));
        request.setEndY(new BigDecimal("2"));
        return request;
    }

    private MapUploadRequest uploadRequest(String commandId) {
        MapUploadRequest request = new MapUploadRequest();
        request.setCommandId(commandId);
        request.setMapImage(
                new MockMultipartFile("mapImage", "map.png", "image/png", new byte[] {1, 2, 3}));
        request.setResolution(new BigDecimal("0.05"));
        request.setOriginX(BigDecimal.ZERO);
        request.setOriginY(BigDecimal.ZERO);
        request.setOriginYaw(BigDecimal.ZERO);
        return request;
    }

    private record Fixture(ApartmentComplex apartment, PatrolRobot robot, PatrolMap map) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        @Primary
        FakeMapFileStorage fakeMapFileStorage() {
            return new FakeMapFileStorage();
        }
    }

    static final class FakeMapFileStorage extends MapFileStorage {

        private final AtomicInteger stores = new AtomicInteger();

        private FakeMapFileStorage() {
            super(new FileStorageProperties());
        }

        @Override
        public StoredMapFile store(MultipartFile file) {
            int number = stores.incrementAndGet();
            return new StoredMapFile(
                    "test-" + number + ".png", "/api/map/files/test-" + number + ".png", 120, 80);
        }

        @Override
        public void deleteByUrl(String mapUrl) {}

        int storeCount() {
            return stores.get();
        }
    }
}
