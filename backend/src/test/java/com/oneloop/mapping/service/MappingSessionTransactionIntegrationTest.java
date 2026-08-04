package com.oneloop.mapping.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.dto.mqtt.StartMappingCommand;
import com.oneloop.mapping.dto.request.MappingStartRequest;
import com.oneloop.mapping.dto.response.MappingStartResponse;
import com.oneloop.mapping.repository.MappingSessionRepository;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.repository.RobotRepository;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;

@ActiveProfiles("test")
@SpringBootTest
@Import(MappingSessionTransactionIntegrationTest.TestConfig.class)
class MappingSessionTransactionIntegrationTest {

    @Autowired private MappingSessionService mappingSessionService;
    @Autowired private ApartmentComplexRepository apartmentComplexRepository;
    @Autowired private RobotRepository robotRepository;
    @Autowired private MappingSessionRepository mappingSessionRepository;
    @Autowired private ControllableMappingPublisher mappingPublisher;

    @BeforeEach
    void acknowledgeMappingStartImmediately() {
        mappingPublisher.acknowledgeImmediately();
    }

    @Test
    void immediateAckFromAnotherTransactionReadsCommittedMappingSession() {
        Fixture fixture = createFixture();
        MappingStartResponse[] response = new MappingStartResponse[1];

        assertThatCode(
                        () ->
                                response[0] =
                                        mappingSessionService.start(
                                                fixture.complex().getId(),
                                                new MappingStartRequest(fixture.robot().getId())))
                .doesNotThrowAnyException();

        assertThat(mappingSessionRepository.findById(response[0].getMappingSessionId()))
                .get()
                .satisfies(
                        session -> {
                            assertThat(session.getStatus()).isEqualTo(MappingStatus.MAPPING);
                            assertThat(session.getStartedAt()).isNotNull();
                        });
    }

    @ParameterizedTest
    @EnumSource(
            value = MappingStatus.class,
            names = {"COMPLETED", "FAILED", "CANCELLED"})
    void terminalSessionDoesNotBlockRemapping(MappingStatus terminalStatus) {
        Fixture fixture = createFixture();
        MappingSession previous = persistSession(fixture, terminalStatus);
        String previousCommandId = previous.getCommandId();
        long sessionCount = mappingSessionRepository.count();

        MappingStartResponse response =
                mappingSessionService.start(
                        fixture.complex().getId(),
                        new MappingStartRequest(fixture.robot().getId()));

        assertThat(response.getMappingSessionId()).isEqualTo(previous.getId());
        assertThat(mappingSessionRepository.count()).isEqualTo(sessionCount);
        assertThat(mappingSessionRepository.findById(response.getMappingSessionId()))
                .get()
                .satisfies(
                        session -> {
                            assertThat(session.getStatus()).isEqualTo(MappingStatus.MAPPING);
                            assertThat(session.getCommandId()).isNotEqualTo(previousCommandId);
                            assertThat(session.getStartedAt()).isNotNull();
                            assertThat(session.getFinishedAt()).isNull();
                        });
    }

    @ParameterizedTest
    @EnumSource(value = MappingStatus.class, names = {"REQUESTED", "MAPPING"})
    void activeSessionBlocksAnotherMappingStart(MappingStatus activeStatus) {
        Fixture fixture = createFixture();
        persistSession(fixture, activeStatus);

        assertThatThrownBy(
                        () ->
                                mappingSessionService.start(
                                        fixture.complex().getId(),
                                        new MappingStartRequest(fixture.robot().getId())))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAPPING_SESSION_ALREADY_ACTIVE));
    }

    @Test
    void publishFailureCompensatesRequestedSessionToFailed() {
        Fixture fixture = createFixture();
        mappingPublisher.failPublish();

        assertThatThrownBy(
                        () ->
                                mappingSessionService.start(
                                        fixture.complex().getId(),
                                        new MappingStartRequest(fixture.robot().getId())))
                .isInstanceOf(BusinessException.class);

        assertThat(mappingSessionRepository.findById(mappingPublisher.lastMappingSessionId()))
                .get()
                .extracting(MappingSession::getStatus)
                .isEqualTo(MappingStatus.FAILED);
    }

    @Test
    void terminalSessionOwnedByAnotherRobotIsRejected() {
        Fixture fixture = createFixture();
        PatrolRobot otherRobot =
                robotRepository.saveAndFlush(
                        new PatrolRobot(
                                fixture.complex(),
                                "other-mapping-robot",
                                "other-mapping-" + UUID.randomUUID()));
        persistSession(new Fixture(fixture.complex(), otherRobot), MappingStatus.COMPLETED);

        assertThatThrownBy(
                        () ->
                                mappingSessionService.start(
                                        fixture.complex().getId(),
                                        new MappingStartRequest(fixture.robot().getId())))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAPPING_SESSION_ALREADY_EXISTS));
    }

    private Fixture createFixture() {
        ApartmentComplex complex =
                apartmentComplexRepository.saveAndFlush(
                        new ApartmentComplex(
                                "mapping-transaction-" + UUID.randomUUID(),
                                "integration-test-address",
                                "00000"));
        PatrolRobot robot =
                robotRepository.saveAndFlush(
                        new PatrolRobot(
                                complex,
                                "mapping-transaction-robot",
                                "mapping-transaction-" + UUID.randomUUID()));
        return new Fixture(complex, robot);
    }

    private MappingSession persistSession(Fixture fixture, MappingStatus status) {
        MappingSession session =
                new MappingSession(
                        fixture.complex(), fixture.robot(), UUID.randomUUID().toString());
        ReflectionTestUtils.setField(session, "status", status);
        if (status != MappingStatus.REQUESTED) {
            ReflectionTestUtils.setField(
                    session, "startedAt", LocalDateTime.now().minusMinutes(2));
        }
        if (status != MappingStatus.REQUESTED && status != MappingStatus.MAPPING) {
            ReflectionTestUtils.setField(
                    session, "finishedAt", LocalDateTime.now().minusMinutes(1));
        }
        return mappingSessionRepository.saveAndFlush(session);
    }

    private record Fixture(ApartmentComplex complex, PatrolRobot robot) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        @Primary
        ControllableMappingPublisher mappingPublisher(MappingCommandAckService ackService) {
            return new ControllableMappingPublisher(ackService);
        }
    }

    static final class ControllableMappingPublisher extends MqttPublisher {

        private final MappingCommandAckService ackService;
        private volatile boolean shouldFail;
        private volatile Long lastMappingSessionId;

        private ControllableMappingPublisher(MappingCommandAckService ackService) {
            super(null);
            this.ackService = ackService;
        }

        void acknowledgeImmediately() {
            shouldFail = false;
            lastMappingSessionId = null;
        }

        void failPublish() {
            shouldFail = true;
            lastMappingSessionId = null;
        }

        Long lastMappingSessionId() {
            return lastMappingSessionId;
        }

        @Override
        public void publishCommand(String robotKey, Object command) {
            if (!(command instanceof StartMappingCommand startCommand)) {
                return;
            }
            lastMappingSessionId = startCommand.mappingSessionId();
            if (shouldFail) {
                throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
            }

            CompletableFuture.runAsync(
                            () ->
                                    ackService.handle(
                                            robotKey,
                                            new CommandAck(
                                                    1,
                                                    startCommand.commandId(),
                                                    startCommand.command(),
                                                    CommandAck.AckStatus.SUCCEEDED,
                                                    OffsetDateTime.now())))
                    .orTimeout(5, TimeUnit.SECONDS)
                    .join();
        }
    }
}
