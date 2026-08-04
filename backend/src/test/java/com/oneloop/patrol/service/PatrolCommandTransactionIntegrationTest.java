package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StartPatrolCommand;
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
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
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
    @Autowired private ApartmentComplexRepository apartmentComplexRepository;
    @Autowired private RobotRepository robotRepository;
    @Autowired private PatrolRepository patrolRepository;
    @Autowired private PatrolMapRepository patrolMapRepository;
    @Autowired private CheckpointRepository checkpointRepository;

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
        checkpointRepository.saveAndFlush(
                new Checkpoint(
                        patrolMap,
                        CheckpointType.DESTINATION,
                        "transaction-race-destination",
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        BigDecimal.ONE,
                        BigDecimal.ONE));

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

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        @Primary
        MqttPublisher immediateRejectingPublisher(PatrolCommandAckService ackService) {
            return new ImmediateRejectingPublisher(ackService);
        }
    }

    private static final class ImmediateRejectingPublisher extends MqttPublisher {

        private final PatrolCommandAckService ackService;

        private ImmediateRejectingPublisher(PatrolCommandAckService ackService) {
            super(null);
            this.ackService = ackService;
        }

        @Override
        public void publishCommand(String robotKey, Object command) {
            if (!(command instanceof StartPatrolCommand startCommand)) {
                return;
            }

            CompletableFuture.runAsync(
                            () ->
                                    ackService.handle(
                                            robotKey,
                                            new CommandAck(
                                                    1,
                                                    startCommand.commandId(),
                                                    startCommand.command(),
                                                    CommandAck.AckStatus.REJECTED,
                                                    OffsetDateTime.now())))
                    .orTimeout(5, TimeUnit.SECONDS)
                    .join();
        }
    }
}
