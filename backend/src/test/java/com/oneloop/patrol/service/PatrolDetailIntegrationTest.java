package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.dto.response.PatrolDetailResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@SpringBootTest
class PatrolDetailIntegrationTest {

    @Autowired private ApartmentComplexRepository apartmentComplexRepository;
    @Autowired private RobotRepository robotRepository;
    @Autowired private PatrolMapRepository patrolMapRepository;
    @Autowired private CheckpointRepository checkpointRepository;
    @Autowired private NavigationWaypointRepository navigationWaypointRepository;
    @Autowired private PatrolRepository patrolRepository;
    @Autowired private PatrolService patrolService;

    @Test
    void detailUsesPatrolSnapshotMapNotCurrentActive() {
        String unique = "patrol-detail-" + UUID.randomUUID();
        ApartmentComplex apartment =
                apartmentComplexRepository.saveAndFlush(
                        new ApartmentComplex(unique, "integration-address", "00000"));
        PatrolRobot robot =
                robotRepository.saveAndFlush(new PatrolRobot(apartment, "robot", unique));
        PatrolMap firstMap =
                patrolMapRepository.saveAndFlush(
                        new PatrolMap(
                                apartment,
                                "first map",
                                "/api/map/files/first-" + unique + ".png",
                                new BigDecimal("0.05"),
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                100,
                                100));
        apartment.assignActiveMap(firstMap);
        apartmentComplexRepository.saveAndFlush(apartment);

        Checkpoint zone =
                checkpointRepository.saveAndFlush(
                        new Checkpoint(
                                firstMap,
                                CheckpointType.PARKING,
                                "snapshot parking",
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ONE,
                                BigDecimal.ONE));
        navigationWaypointRepository.saveAndFlush(
                new NavigationWaypoint(
                        firstMap,
                        firstMap.getMapVersion(),
                        1,
                        new BigDecimal("0.5"),
                        new BigDecimal("0.5"),
                        NavigationWaypointAction.DESTINATION,
                        null,
                        new BigDecimal("0.3"),
                        zone));

        Patrol patrol =
                patrolRepository.saveAndFlush(
                        new Patrol(
                                robot,
                                firstMap,
                                LocalDateTime.now().minusMinutes(10),
                                UUID.randomUUID().toString()));
        patrol.complete();
        patrol = patrolRepository.saveAndFlush(patrol);

        PatrolMap secondMap =
                patrolMapRepository.saveAndFlush(
                        new PatrolMap(
                                apartment,
                                "second map",
                                "/api/map/files/second-" + unique + ".png",
                                new BigDecimal("0.05"),
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                120,
                                120));
        firstMap.archive();
        patrolMapRepository.saveAndFlush(firstMap);
        apartment.assignActiveMap(secondMap);
        apartmentComplexRepository.saveAndFlush(apartment);

        PatrolMap currentActive =
                patrolMapRepository
                        .findByApartmentComplexId(apartment.getId())
                        .orElseThrow();
        assertThat(currentActive.getId()).isEqualTo(secondMap.getId());

        PatrolDetailResponse detail = patrolService.findDetail(apartment.getId(), patrol.getId());

        assertThat(detail.getMapId()).isEqualTo(firstMap.getId());
        assertThat(detail.getMapVersion()).isEqualTo(firstMap.getMapVersion());
        assertThat(detail.getMapUrl()).isEqualTo(firstMap.getUrl());
        assertThat(detail.getMapUrl()).isNotEqualTo(currentActive.getUrl());
    }

    @Test
    void legacyPatrolWithoutMapSnapshotReturnsNullMapUrl() {
        String unique = "legacy-patrol-" + UUID.randomUUID();
        ApartmentComplex apartment =
                apartmentComplexRepository.saveAndFlush(
                        new ApartmentComplex(unique, "integration-address", "00000"));
        PatrolRobot robot =
                robotRepository.saveAndFlush(new PatrolRobot(apartment, "robot", unique));

        Patrol patrol =
                patrolRepository.saveAndFlush(
                        new Patrol(
                                robot,
                                LocalDateTime.now().minusMinutes(5),
                                UUID.randomUUID().toString()));
        patrol.complete();
        patrol = patrolRepository.saveAndFlush(patrol);

        PatrolDetailResponse detail = patrolService.findDetail(apartment.getId(), patrol.getId());

        assertThat(detail.getMapId()).isNull();
        assertThat(detail.getMapVersion()).isNull();
        assertThat(detail.getMapUrl()).isNull();
    }
}
