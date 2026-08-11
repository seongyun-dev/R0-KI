package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import com.oneloop.patrol.repository.PatrolCheckpointVisitRepository;
import com.oneloop.robot.domain.PatrolRobot;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class PatrolCheckpointVisitRecorderTest {

    private static final LocalDateTime STARTED_AT =
            LocalDateTime.of(2026, 8, 11, 12, 0, 0);

    @Mock private CheckpointRepository checkpointRepository;
    @Mock private PatrolCheckpointVisitRepository patrolCheckpointVisitRepository;

    private PatrolCheckpointVisitRecorder recorder;
    private Patrol patrol;
    private PatrolMap patrolMap;
    private Checkpoint firstZone;
    private Checkpoint secondZone;

    @BeforeEach
    void setUp() {
        ApartmentComplex apartment = new ApartmentComplex("complex", "address", "00000");
        PatrolRobot robot = new PatrolRobot(apartment, "robot", "robot-101");
        patrol = new Patrol(robot, STARTED_AT, UUID.randomUUID().toString());
        ReflectionTestUtils.setField(patrol, "id", 29L);

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

        firstZone = checkpoint(41L, "first", "0", "0", "1", "1");
        secondZone = checkpoint(42L, "second", "2", "0", "3", "1");
        recorder =
                new PatrolCheckpointVisitRecorder(
                        checkpointRepository,
                        patrolCheckpointVisitRepository,
                        new CheckpointLocator());
    }

    @Test
    void recordsFirstZoneVisitWithSequenceOne() {
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(firstZone, secondZone));
        when(patrolCheckpointVisitRepository.findFirstByPatrolIdOrderByVisitSequenceDesc(29L))
                .thenReturn(Optional.empty());
        LocalDateTime visitedAt = STARTED_AT.plusSeconds(1);

        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("0.5"),
                new BigDecimal("0.5"),
                visitedAt);

        ArgumentCaptor<PatrolCheckpointVisit> captor =
                ArgumentCaptor.forClass(PatrolCheckpointVisit.class);
        verify(patrolCheckpointVisitRepository).save(captor.capture());
        assertThat(captor.getValue().getPatrol()).isSameAs(patrol);
        assertThat(captor.getValue().getCheckpoint()).isSameAs(firstZone);
        assertThat(captor.getValue().getVisitSequence()).isEqualTo(1);
        assertThat(captor.getValue().getVisitedAt()).isEqualTo(visitedAt);
    }

    @Test
    void doesNotRepeatTheSameZoneOnConsecutivePoseMessages() {
        PatrolCheckpointVisit latest =
                new PatrolCheckpointVisit(
                        patrol, firstZone, 1, STARTED_AT.plusSeconds(1));
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(firstZone));
        when(patrolCheckpointVisitRepository.findFirstByPatrolIdOrderByVisitSequenceDesc(29L))
                .thenReturn(Optional.of(latest));

        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("0.8"),
                new BigDecimal("0.8"),
                STARTED_AT.plusSeconds(2));

        verify(patrolCheckpointVisitRepository, never()).save(any());
    }

    @Test
    void recordsAChangedZoneWithTheNextSequence() {
        PatrolCheckpointVisit latest =
                new PatrolCheckpointVisit(
                        patrol, firstZone, 3, STARTED_AT.plusSeconds(3));
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(firstZone, secondZone));
        when(patrolCheckpointVisitRepository.findFirstByPatrolIdOrderByVisitSequenceDesc(29L))
                .thenReturn(Optional.of(latest));

        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("2.5"),
                new BigDecimal("0.5"),
                STARTED_AT.plusSeconds(4));

        ArgumentCaptor<PatrolCheckpointVisit> captor =
                ArgumentCaptor.forClass(PatrolCheckpointVisit.class);
        verify(patrolCheckpointVisitRepository).save(captor.capture());
        assertThat(captor.getValue().getCheckpoint()).isSameAs(secondZone);
        assertThat(captor.getValue().getVisitSequence()).isEqualTo(4);
    }

    @Test
    void recordsAChangedZonePublishedInTheSameSecond() {
        LocalDateTime reportedAt = STARTED_AT.plusSeconds(3);
        PatrolCheckpointVisit latest =
                new PatrolCheckpointVisit(patrol, firstZone, 3, reportedAt);
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(firstZone, secondZone));
        when(patrolCheckpointVisitRepository.findFirstByPatrolIdOrderByVisitSequenceDesc(29L))
                .thenReturn(Optional.of(latest));

        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("2.5"),
                new BigDecimal("0.5"),
                reportedAt);

        ArgumentCaptor<PatrolCheckpointVisit> captor =
                ArgumentCaptor.forClass(PatrolCheckpointVisit.class);
        verify(patrolCheckpointVisitRepository).save(captor.capture());
        assertThat(captor.getValue().getCheckpoint()).isSameAs(secondZone);
        assertThat(captor.getValue().getVisitSequence()).isEqualTo(4);
    }

    @Test
    void ignoresPoseOutsideEveryZone() {
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(firstZone, secondZone));

        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("1.5"),
                new BigDecimal("0.5"),
                STARTED_AT.plusSeconds(1));

        verifyNoInteractions(patrolCheckpointVisitRepository);
    }

    @Test
    void ignoresPoseReportedBeforeThePatrolStarted() {
        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("0.5"),
                new BigDecimal("0.5"),
                STARTED_AT.minusNanos(1));

        verifyNoInteractions(checkpointRepository, patrolCheckpointVisitRepository);
    }

    @Test
    void ignoresPoseOlderThanTheLatestVisit() {
        PatrolCheckpointVisit latest =
                new PatrolCheckpointVisit(
                        patrol, firstZone, 2, STARTED_AT.plusSeconds(5));
        when(checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(31L))
                .thenReturn(List.of(firstZone, secondZone));
        when(patrolCheckpointVisitRepository.findFirstByPatrolIdOrderByVisitSequenceDesc(29L))
                .thenReturn(Optional.of(latest));

        recorder.recordEntry(
                patrol,
                patrolMap,
                new BigDecimal("2.5"),
                new BigDecimal("0.5"),
                STARTED_AT.plusSeconds(4));

        verify(patrolCheckpointVisitRepository, never()).save(any());
    }

    private Checkpoint checkpoint(
            Long id, String name, String minX, String minY, String maxX, String maxY) {
        Checkpoint checkpoint =
                new Checkpoint(
                        patrolMap,
                        CheckpointType.PARKING,
                        name,
                        new BigDecimal(minX),
                        new BigDecimal(minY),
                        new BigDecimal(maxX),
                        new BigDecimal(maxY));
        ReflectionTestUtils.setField(checkpoint, "id", id);
        return checkpoint;
    }
}
