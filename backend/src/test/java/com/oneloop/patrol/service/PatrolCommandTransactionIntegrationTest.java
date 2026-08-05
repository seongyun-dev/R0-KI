package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.ZoneBatchCreateRequest;
import com.oneloop.map.dto.request.ZoneCreateRequest;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.service.ZoneService;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StartPatrolCommand;
import com.oneloop.patrol.dto.mqtt.StopPatrolCommand;
import com.oneloop.patrol.dto.request.PatrolStartRequest;
import com.oneloop.patrol.dto.response.PatrolStartResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@SpringBootTest
@Import(PatrolCommandTransactionIntegrationTest.TestConfig.class)
class PatrolCommandTransactionIntegrationTest {

    @Autowired private PatrolCommandService patrolCommandService;
    @Autowired private PatrolCommandStateService patrolCommandStateService;
    @Autowired private ApartmentComplexRepository apartmentComplexRepository;
    @Autowired private RobotRepository robotRepository;
    @Autowired private PatrolRepository patrolRepository;
    @Autowired private PatrolMapRepository patrolMapRepository;
    @Autowired private CheckpointRepository checkpointRepository;
    @Autowired private NavigationWaypointRepository navigationWaypointRepository;
    @Autowired private ZoneService zoneService;
    @Autowired private ImmediateAckPublisher immediateAckPublisher;

    @Test
    void immediateAckFromAnotherTransactionReadsCommittedStartCommand() {
        ApartmentComplex complex =
                apartmentComplexRepository.save(
                        new ApartmentComplex(
                                "transaction-race-" + UUID.randomUUID(),
                                "integration-test-address",
                                "00000"));
        PatrolRobot robot =
                new PatrolRobot(
                        complex,
                        "transaction-race-robot",
                        "transaction-race-" + UUID.randomUUID());
        LocalDateTime receivedAt = LocalDateTime.now();
        robot.updateStatus(
                RobotStatus.IDLE,
                new BigDecimal("80"),
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                SensorStatus.DISCONNECTED,
                receivedAt,
                null,
                null);
        robot.recordConnection(receivedAt);
        robotRepository.saveAndFlush(robot);
        PatrolMap patrolMap =
                patrolMapRepository.saveAndFlush(
                        new PatrolMap(
                                complex,
                                "transaction-race-map",
                                "/api/map/files/transaction-race-" + UUID.randomUUID() + ".png",
                                new BigDecimal("0.05"),
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                100,
                                100));
        Checkpoint destination =
                checkpointRepository.saveAndFlush(
                        new Checkpoint(
                                patrolMap,
                                CheckpointType.DESTINATION,
                                "transaction-race-destination",
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ONE,
                                BigDecimal.ONE));
        navigationWaypointRepository.saveAndFlush(
                new NavigationWaypoint(
                        patrolMap,
                        patrolMap.getMapVersion(),
                        1,
                        new BigDecimal("0.5"),
                        new BigDecimal("0.5"),
                        NavigationWaypointAction.DESTINATION,
                        null,
                        new BigDecimal("0.3"),
                        destination));

        PatrolStartResponse[] response = new PatrolStartResponse[1];
        assertThatCode(
                        () ->
                                response[0] =
                                        patrolCommandService.start(
                                                complex.getId(),
                                                new PatrolStartRequest(robot.getId())))
                .doesNotThrowAnyException();

        assertThat(patrolRepository.findById(response[0].getPatrolId()))
                .get()
                .extracting(patrol -> patrol.getStatus())
                .isEqualTo(PatrolStatus.FAILED);
    }

    @Test
    void automaticCompletionCommitsStopCommandBeforeImmediateAck() {
        ApartmentComplex complex =
                apartmentComplexRepository.save(
                        new ApartmentComplex(
                                "stop-race-" + UUID.randomUUID(),
                                "integration-test-address",
                                "00000"));
        PatrolRobot robot =
                robotRepository.saveAndFlush(
                        new PatrolRobot(
                                complex, "stop-race-robot", "stop-race-" + UUID.randomUUID()));
        PatrolMap patrolMap =
                patrolMapRepository.saveAndFlush(
                        new PatrolMap(
                                complex,
                                "stop-race-map",
                                "/api/map/files/stop-race-" + UUID.randomUUID() + ".png",
                                new BigDecimal("0.05"),
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                100,
                                100));
        Checkpoint destination =
                checkpointRepository.saveAndFlush(
                        new Checkpoint(
                                patrolMap,
                                CheckpointType.DESTINATION,
                                "stop-race-destination",
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ONE,
                                BigDecimal.ONE));
        navigationWaypointRepository.saveAndFlush(
                new NavigationWaypoint(
                        patrolMap,
                        patrolMap.getMapVersion(),
                        1,
                        new BigDecimal("0.5"),
                        new BigDecimal("0.5"),
                        NavigationWaypointAction.DESTINATION,
                        null,
                        new BigDecimal("0.3"),
                        destination));
        Patrol patrol =
                patrolRepository.saveAndFlush(
                        new Patrol(
                                robot,
                                LocalDateTime.now().minusMinutes(1),
                                UUID.randomUUID().toString()));
        immediateAckPublisher.resetStopCommandVisible();

        patrolCommandService.autoCompleteIfArrived(
                robot, new BigDecimal("0.5"), new BigDecimal("0.5"));

        assertThat(immediateAckPublisher.isStopCommandVisible()).isTrue();
        assertThat(patrolRepository.findById(patrol.getId()))
                .get()
                .extracting(Patrol::getStatus)
                .isEqualTo(PatrolStatus.COMPLETED);
    }

    @Test
    void concurrentStartsForSameRobotCreateExactlyOneActivePatrol() throws InterruptedException {
        StartFixture fixture = readyFixture("concurrent-start");
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        CompletableFuture<OperationResult> first =
                CompletableFuture.supplyAsync(
                        () ->
                                runAfterGate(
                                        ready,
                                        start,
                                        () ->
                                                patrolCommandStateService.prepareStart(
                                                        fixture.apartment().getId(),
                                                        new PatrolStartRequest(
                                                                fixture.robot().getId()))));
        CompletableFuture<OperationResult> second =
                CompletableFuture.supplyAsync(
                        () ->
                                runAfterGate(
                                        ready,
                                        start,
                                        () ->
                                                patrolCommandStateService.prepareStart(
                                                        fixture.apartment().getId(),
                                                        new PatrolStartRequest(
                                                                fixture.robot().getId()))));

        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        start.countDown();
        List<OperationResult> results =
                List.of(
                        first.orTimeout(5, TimeUnit.SECONDS).join(),
                        second.orTimeout(5, TimeUnit.SECONDS).join());

        assertThat(results).filteredOn(OperationResult::succeeded).hasSize(1);
        assertThat(results)
                .filteredOn(result -> result.errorCode() == ErrorCode.PATROL_ALREADY_IN_PROGRESS)
                .hasSize(1);
        assertThat(activePatrols(fixture.robot().getId())).hasSize(1);
    }

    @Test
    void startAndZoneReplacementSerializeOnCurrentMap() throws InterruptedException {
        StartFixture fixture = readyFixture("start-zone-race");
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ZoneBatchCreateRequest zoneRequest = replacementZoneRequest(fixture.map().getMapVersion());

        CompletableFuture<OperationResult> startResultFuture =
                CompletableFuture.supplyAsync(
                        () ->
                                runAfterGate(
                                        ready,
                                        start,
                                        () ->
                                                patrolCommandStateService.prepareStart(
                                                        fixture.apartment().getId(),
                                                        new PatrolStartRequest(
                                                                fixture.robot().getId()))));
        CompletableFuture<OperationResult> zoneResultFuture =
                CompletableFuture.supplyAsync(
                        () ->
                                runAfterGate(
                                        ready,
                                        start,
                                        () ->
                                                zoneService.createAll(
                                                        fixture.apartment().getId(),
                                                        fixture.map().getId(),
                                                        zoneRequest)));

        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        start.countDown();
        OperationResult startResult = startResultFuture.orTimeout(5, TimeUnit.SECONDS).join();
        OperationResult zoneResult = zoneResultFuture.orTimeout(5, TimeUnit.SECONDS).join();

        if (startResult.succeeded()) {
            assertThat(zoneResult.errorCode()).isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED);
            assertThat(activePatrols(fixture.robot().getId())).hasSize(1);
            assertThat(
                            navigationWaypointRepository
                                    .findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                                            fixture.map().getId(), fixture.map().getMapVersion()))
                    .hasSize(1);
        } else {
            assertThat(startResult.errorCode()).isEqualTo(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
            assertThat(zoneResult.succeeded()).isTrue();
            assertThat(activePatrols(fixture.robot().getId())).isEmpty();
            assertThat(
                            navigationWaypointRepository
                                    .findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                                            fixture.map().getId(), fixture.map().getMapVersion()))
                    .isEmpty();
        }
    }

    private StartFixture readyFixture(String prefix) {
        String unique = prefix + "-" + UUID.randomUUID();
        ApartmentComplex apartment =
                apartmentComplexRepository.saveAndFlush(
                        new ApartmentComplex(unique, "integration-test-address", "00000"));
        PatrolRobot robot = new PatrolRobot(apartment, "robot", unique);
        LocalDateTime receivedAt = LocalDateTime.now();
        robot.updateStatus(
                RobotStatus.IDLE,
                new BigDecimal("80"),
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                SensorStatus.NORMAL,
                SensorStatus.DISCONNECTED,
                receivedAt,
                null,
                null);
        robot.recordConnection(receivedAt);
        robotRepository.saveAndFlush(robot);
        PatrolMap patrolMap =
                patrolMapRepository.saveAndFlush(
                        new PatrolMap(
                                apartment,
                                "map",
                                "/api/map/files/" + unique + ".png",
                                new BigDecimal("0.05"),
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                100,
                                100));
        Checkpoint destination =
                checkpointRepository.saveAndFlush(
                        new Checkpoint(
                                patrolMap,
                                CheckpointType.DESTINATION,
                                "destination",
                                BigDecimal.ZERO,
                                BigDecimal.ZERO,
                                BigDecimal.ONE,
                                BigDecimal.ONE));
        navigationWaypointRepository.saveAndFlush(
                new NavigationWaypoint(
                        patrolMap,
                        patrolMap.getMapVersion(),
                        1,
                        new BigDecimal("0.5"),
                        new BigDecimal("0.5"),
                        NavigationWaypointAction.DESTINATION,
                        null,
                        new BigDecimal("0.3"),
                        destination));
        return new StartFixture(apartment, robot, patrolMap);
    }

    private ZoneBatchCreateRequest replacementZoneRequest(Integer mapVersion) {
        ZoneCreateRequest zone = new ZoneCreateRequest();
        zone.setType(CheckpointType.PARKING);
        zone.setName("replacement parking");
        zone.setStartX(BigDecimal.ZERO);
        zone.setStartY(BigDecimal.ZERO);
        zone.setEndX(new BigDecimal("2"));
        zone.setEndY(new BigDecimal("2"));
        ZoneBatchCreateRequest request = new ZoneBatchCreateRequest();
        request.setMapVersion(mapVersion);
        request.setZones(List.of(zone));
        return request;
    }

    private List<Patrol> activePatrols(Long robotId) {
        return patrolRepository.findAllByRobotIdInAndStatusInOrderByStartedAtDesc(
                List.of(robotId), List.of(PatrolStatus.IN_PROGRESS, PatrolStatus.STOP_REQUESTED));
    }

    private OperationResult runAfterGate(
            CountDownLatch ready, CountDownLatch start, Runnable operation) {
        ready.countDown();
        try {
            start.await();
            operation.run();
            return new OperationResult(true, null);
        } catch (BusinessException exception) {
            return new OperationResult(false, exception.getErrorCode());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AssertionError("동시성 테스트 대기 중 인터럽트가 발생했습니다.", exception);
        }
    }

    private record StartFixture(ApartmentComplex apartment, PatrolRobot robot, PatrolMap map) {}

    private record OperationResult(boolean succeeded, ErrorCode errorCode) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        @Primary
        ImmediateAckPublisher immediateAckPublisher(
                PatrolCommandAckService ackService, PatrolRepository patrolRepository) {
            return new ImmediateAckPublisher(ackService, patrolRepository);
        }

        @Bean
        @Primary
        PatrolAiSummaryService noOpPatrolAiSummaryService() {
            return new PatrolAiSummaryService(null, null) {
                @Override
                public void requestGeneration(Long patrolId) {}
            };
        }
    }

    static final class ImmediateAckPublisher extends MqttPublisher {

        private final PatrolCommandAckService ackService;
        private final PatrolRepository patrolRepository;
        private final AtomicBoolean stopCommandVisible = new AtomicBoolean();

        private ImmediateAckPublisher(
                PatrolCommandAckService ackService, PatrolRepository patrolRepository) {
            super(null);
            this.ackService = ackService;
            this.patrolRepository = patrolRepository;
        }

        @Override
        public void publishCommand(String robotKey, Object command) {
            if (command instanceof StartPatrolCommand startCommand) {
                runAsyncAck(
                        robotKey,
                        startCommand.commandId(),
                        startCommand.command(),
                        CommandAck.AckStatus.REJECTED);
            } else if (command instanceof StopPatrolCommand stopCommand) {
                CompletableFuture.runAsync(
                                () -> {
                                    stopCommandVisible.set(
                                            patrolRepository
                                                    .findByCommandId(stopCommand.commandId())
                                                    .isPresent());
                                    ackService.handle(
                                            robotKey,
                                            new CommandAck(
                                                    1,
                                                    stopCommand.commandId(),
                                                    stopCommand.command(),
                                                    CommandAck.AckStatus.SUCCEEDED,
                                                    OffsetDateTime.now()));
                                })
                        .orTimeout(5, TimeUnit.SECONDS)
                        .join();
            }
        }

        private void runAsyncAck(
                String robotKey, String commandId, String command, CommandAck.AckStatus status) {
            CompletableFuture.runAsync(
                            () ->
                                    ackService.handle(
                                            robotKey,
                                            new CommandAck(
                                                    1,
                                                    commandId,
                                                    command,
                                                    status,
                                                    OffsetDateTime.now())))
                    .orTimeout(5, TimeUnit.SECONDS)
                    .join();
        }

        boolean isStopCommandVisible() {
            return stopCommandVisible.get();
        }

        void resetStopCommandVisible() {
            stopCommandVisible.set(false);
        }
    }
}
