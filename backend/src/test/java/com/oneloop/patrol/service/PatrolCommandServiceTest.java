package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.util.CheckpointLocator;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StartPatrolCommand;
import com.oneloop.patrol.dto.request.PatrolStartRequest;
import com.oneloop.patrol.dto.response.PatrolStartResponse;
import com.oneloop.patrol.dto.response.PatrolStopResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.domain.SensorStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class PatrolCommandServiceTest {

    @Mock private PatrolRepository patrolRepository;
    @Mock private RobotRepository robotRepository;
    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private CheckpointRepository checkpointRepository;
    @Mock private CheckpointLocator checkpointLocator;
    @Mock private PatrolAiSummaryService patrolAiSummaryService;
    @Mock private ObjectProvider<MqttPublisher> mqttPublisherProvider;
    @Mock private MqttPublisher mqttPublisher;
    @Mock private ApartmentComplex apartmentComplex;
    @Mock private PatrolMap patrolMap;

    @Test
    void disconnectedLineSensorDoesNotBlockWaypointPatrolWhenExactlyOneDestinationExists() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolRepository.save(any(Patrol.class)))
                .thenAnswer(
                        invocation -> {
                            Patrol patrol = invocation.getArgument(0);
                            ReflectionTestUtils.setField(patrol, "id", 29L);
                            return patrol;
                        });
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);
        stubSingleDestination();

        PatrolStartResponse response = service().start(2L, new PatrolStartRequest(17L));

        assertThat(response.getPatrolId()).isEqualTo(29L);
        verify(mqttPublisher).publishCommand(any(String.class), any(StartPatrolCommand.class));
    }

    @Test
    void missingMapBlocksPatrolBeforeCommandIsSaved() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolMapRepository.findByApartmentComplexId(2L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service().start(2L, new PatrolStartRequest(17L)))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.ROBOT_NOT_READY));
        verify(patrolRepository, never()).save(any(Patrol.class));
    }

    @ParameterizedTest
    @ValueSource(longs = {0L, 2L})
    void missingOrDuplicateDestinationBlocksPatrolBeforeCommandIsSaved(
            long destinationCount) {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolMapRepository.findByApartmentComplexId(2L))
                .thenReturn(Optional.of(patrolMap));
        when(patrolMap.getId()).thenReturn(31L);
        when(checkpointRepository.countByPatrolMapIdAndType(
                        31L, CheckpointType.DESTINATION))
                .thenReturn(destinationCount);

        assertThatThrownBy(() -> service().start(2L, new PatrolStartRequest(17L)))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.ROBOT_NOT_READY));
        verify(patrolRepository, never()).save(any(Patrol.class));
    }

    @ParameterizedTest
    @ValueSource(strings = {"camera", "lidar", "motor"})
    void requiredModuleStillBlocksPatrolWhenDisconnected(String disconnectedModule) {
        PatrolRobot robot =
                readyRobot(
                        statusFor("camera", disconnectedModule),
                        statusFor("lidar", disconnectedModule),
                        statusFor("motor", disconnectedModule),
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));

        assertThatThrownBy(() -> service().start(2L, new PatrolStartRequest(17L)))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.ROBOT_NOT_READY));
    }

    @Test
    void immediateRejectedAckCanSeePreparedCommandBeforePublishReturns() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        AtomicReference<Patrol> savedPatrol = new AtomicReference<>();
        when(robotRepository.findByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolRepository.save(any(Patrol.class)))
                .thenAnswer(
                        invocation -> {
                            Patrol patrol = invocation.getArgument(0);
                            ReflectionTestUtils.setField(patrol, "id", 29L);
                            savedPatrol.set(patrol);
                            return patrol;
                        });
        when(patrolRepository.findByCommandId(anyString()))
                .thenAnswer(
                        invocation -> {
                            Patrol patrol = savedPatrol.get();
                            return patrol != null
                                            && patrol.getCommandId().equals(invocation.getArgument(0))
                                    ? Optional.of(patrol)
                                    : Optional.empty();
                        });
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);
        stubSingleDestination();
        doAnswer(
                        invocation -> {
                            StartPatrolCommand command = invocation.getArgument(1);
                            new PatrolCommandAckService(patrolRepository)
                                    .handle(
                                            "test-101",
                                            new CommandAck(
                                                    1,
                                                    command.commandId(),
                                                    command.command(),
                                                    CommandAck.AckStatus.REJECTED,
                                                    OffsetDateTime.now()));
                            return null;
                        })
                .when(mqttPublisher)
                .publishCommand(anyString(), any(StartPatrolCommand.class));

        service().start(2L, new PatrolStartRequest(17L));

        assertThat(savedPatrol.get().getStatus()).isEqualTo(PatrolStatus.FAILED);
    }

    @Test
    void startPublishFailureCompensatesCommittedPatrolToFailed() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        AtomicReference<Patrol> savedPatrol = new AtomicReference<>();
        when(robotRepository.findByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolRepository.save(any(Patrol.class)))
                .thenAnswer(
                        invocation -> {
                            Patrol patrol = invocation.getArgument(0);
                            ReflectionTestUtils.setField(patrol, "id", 29L);
                            savedPatrol.set(patrol);
                            return patrol;
                        });
        when(patrolRepository.findById(29L)).thenAnswer(ignored -> Optional.of(savedPatrol.get()));
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);
        stubSingleDestination();
        doThrow(new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR))
                .when(mqttPublisher)
                .publishCommand(anyString(), any(StartPatrolCommand.class));

        assertThatThrownBy(() -> service().start(2L, new PatrolStartRequest(17L)))
                .isInstanceOf(BusinessException.class);

        assertThat(savedPatrol.get().getStatus()).isEqualTo(PatrolStatus.FAILED);
    }

    @Test
    void stopPublishFailureKeepsStopRequestedAndSameEndpointCanRetry() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        Patrol patrol = new Patrol(robot, LocalDateTime.now().minusMinutes(1), "start-command");
        ReflectionTestUtils.setField(patrol, "id", 29L);
        when(patrolRepository.findByIdAndRobotApartmentComplexId(29L, 2L))
                .thenReturn(Optional.of(patrol));
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);
        doThrow(new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR))
                .doNothing()
                .when(mqttPublisher)
                .publishCommand(anyString(), any());

        assertThatThrownBy(() -> service().stop(2L, 29L)).isInstanceOf(BusinessException.class);
        String failedPublishCommandId = patrol.getCommandId();
        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.STOP_REQUESTED);

        PatrolStopResponse response = service().stop(2L, 29L);

        assertThat(response.getPatrolStatus()).isEqualTo(PatrolStatus.STOP_REQUESTED);
        assertThat(patrol.getCommandId()).isNotEqualTo(failedPublishCommandId);
        verify(mqttPublisher, times(2)).publishCommand(anyString(), any());
    }

    private PatrolCommandService service() {
        return new PatrolCommandService(
                patrolRepository,
                patrolMapRepository,
                checkpointRepository,
                checkpointLocator,
                patrolAiSummaryService,
                mqttPublisherProvider,
                new PatrolCommandStateService(
                        patrolRepository,
                        robotRepository,
                        patrolMapRepository,
                        checkpointRepository));
    }

    private void stubSingleDestination() {
        when(patrolMapRepository.findByApartmentComplexId(2L))
                .thenReturn(Optional.of(patrolMap));
        when(patrolMap.getId()).thenReturn(31L);
        when(checkpointRepository.countByPatrolMapIdAndType(
                        31L, CheckpointType.DESTINATION))
                .thenReturn(1L);
    }

    private PatrolRobot readyRobot(
            SensorStatus camera, SensorStatus lidar, SensorStatus motor, SensorStatus lineSensor) {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "demo-robot", "test-101");
        ReflectionTestUtils.setField(robot, "id", 17L);
        robot.updateStatus(
                RobotStatus.IDLE,
                new BigDecimal("80"),
                camera,
                lidar,
                motor,
                lineSensor,
                LocalDateTime.now().minusHours(1),
                null,
                null);
        robot.recordConnection(LocalDateTime.now());
        return robot;
    }

    private SensorStatus statusFor(String module, String disconnectedModule) {
        return module.equals(disconnectedModule) ? SensorStatus.DISCONNECTED : SensorStatus.NORMAL;
    }
}
