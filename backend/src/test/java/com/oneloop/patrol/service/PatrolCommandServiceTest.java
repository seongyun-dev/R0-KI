package com.oneloop.patrol.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.map.service.NavigationWaypointService;
import com.oneloop.mqtt.MqttPublisher;
import com.oneloop.mqtt.dto.CommandAck;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.dto.mqtt.StartPatrolCommand;
import com.oneloop.patrol.dto.mqtt.StopPatrolCommand;
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
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class PatrolCommandServiceTest {

    @Mock private PatrolRepository patrolRepository;
    @Mock private RobotRepository robotRepository;
    @Mock private PatrolMapRepository patrolMapRepository;
    @Mock private NavigationWaypointService navigationWaypointService;
    @Mock private DetectedEventRepository detectedEventRepository;
    @Mock private PatrolCheckpointVisitRecorder patrolCheckpointVisitRecorder;
    @Mock private NavigationWaypoint destinationWaypoint;
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
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
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
    void startLocksRobotThenMapAndChecksActivePatrolAfterCurrentRoute() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
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

        service().start(2L, new PatrolStartRequest(17L));

        InOrder lockAndValidationOrder =
                inOrder(
                        robotRepository,
                        patrolMapRepository,
                        navigationWaypointService,
                        patrolRepository);
        lockAndValidationOrder
                .verify(robotRepository)
                .findForUpdateByIdAndApartmentComplexIdAndStatusNot(17L, 2L, RobotStatus.DELETED);
        lockAndValidationOrder.verify(patrolMapRepository).findForUpdateByApartmentComplexId(2L);
        lockAndValidationOrder
                .verify(navigationWaypointService)
                .requireValidCurrentRoute(patrolMap);
        lockAndValidationOrder
                .verify(patrolRepository)
                .existsByRobotIdAndStatusIn(
                        17L, List.of(PatrolStatus.IN_PROGRESS, PatrolStatus.STOP_REQUESTED));
        lockAndValidationOrder.verify(patrolRepository).save(any(Patrol.class));
    }

    @Test
    void missingMapBlocksPatrolBeforeCommandIsSaved() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        assertThatThrownBy(() -> service().start(2L, new PatrolStartRequest(17L)))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.NAVIGATION_CONFIG_NOT_READY));
        verify(patrolRepository, never()).save(any(Patrol.class));
    }

    @Test
    void invalidNavigationRouteBlocksPatrolBeforeCommandIsSaved() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
                        17L, 2L, RobotStatus.DELETED))
                .thenReturn(Optional.of(robot));
        when(patrolMapRepository.findForUpdateByApartmentComplexId(2L))
                .thenReturn(Optional.of(patrolMap));
        when(navigationWaypointService.requireValidCurrentRoute(patrolMap))
                .thenThrow(new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY));

        assertThatThrownBy(() -> service().start(2L, new PatrolStartRequest(17L)))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.NAVIGATION_CONFIG_NOT_READY));
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
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
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
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
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
                                            && patrol.getCommandId()
                                                    .equals(invocation.getArgument(0))
                                    ? Optional.of(patrol)
                                    : Optional.empty();
                        });
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);
        stubSingleDestination();
        doAnswer(
                        invocation -> {
                            StartPatrolCommand command = invocation.getArgument(1);
                            new PatrolCommandAckService(patrolRepository, patrolAiSummaryService)
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
        when(robotRepository.findForUpdateByIdAndApartmentComplexIdAndStatusNot(
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

    @Test
    void automaticStopPublishFailureIsRetriedWithSameIdOnNextPose() {
        PatrolRobot robot =
                readyRobot(
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.NORMAL,
                        SensorStatus.DISCONNECTED);
        Patrol patrol = new Patrol(robot, LocalDateTime.now().minusMinutes(1), "start-command");
        ReflectionTestUtils.setField(patrol, "id", 29L);
        when(apartmentComplex.getId()).thenReturn(2L);
        when(patrolRepository.findFirstForUpdateByRobotIdOrderByStartedAtDesc(17L))
                .thenReturn(Optional.of(patrol));
        when(patrolMapRepository.findByApartmentComplexId(2L)).thenReturn(Optional.of(patrolMap));
        when(navigationWaypointService.requireValidCurrentRoute(patrolMap))
                .thenReturn(List.of(destinationWaypoint));
        when(destinationWaypoint.getX()).thenReturn(new BigDecimal("2.0"));
        when(destinationWaypoint.getY()).thenReturn(new BigDecimal("0.5"));
        when(destinationWaypoint.getAcceptanceRadius()).thenReturn(new BigDecimal("0.3"));
        when(mqttPublisherProvider.getIfAvailable()).thenReturn(mqttPublisher);
        AtomicReference<String> firstCommandId = new AtomicReference<>();
        doAnswer(
                        invocation -> {
                            StopPatrolCommand command = invocation.getArgument(1);
                            if (firstCommandId.compareAndSet(null, command.commandId())) {
                                throw new BusinessException(ErrorCode.INTERNAL_SERVER_ERROR);
                            }
                            assertThat(command.commandId()).isEqualTo(firstCommandId.get());
                            return null;
                        })
                .when(mqttPublisher)
                .publishCommand(anyString(), any(StopPatrolCommand.class));

        assertThatThrownBy(
                        () ->
                                service()
                                        .autoCompleteIfArrived(
                                                robot,
                                                new BigDecimal("2.0"),
                                                new BigDecimal("0.5"),
                                                LocalDateTime.now()))
                .isInstanceOf(BusinessException.class);
        assertThat(patrol.getStatus()).isEqualTo(PatrolStatus.STOP_REQUESTED);

        service()
                .autoCompleteIfArrived(
                        robot,
                        new BigDecimal("2.0"),
                        new BigDecimal("0.5"),
                        LocalDateTime.now());

        assertThat(patrol.getCommandId()).isEqualTo(firstCommandId.get());
        assertThat(patrol.isCompletionRequested()).isTrue();
        verify(mqttPublisher, times(2)).publishCommand(anyString(), any(StopPatrolCommand.class));
        verify(navigationWaypointService).requireValidCurrentRoute(patrolMap);
        verify(patrolAiSummaryService, never()).requestGeneration(patrol.getId());
    }

    private PatrolCommandService service() {
        return new PatrolCommandService(
                patrolRepository,
                mqttPublisherProvider,
                new PatrolCommandStateService(
                        patrolRepository,
                        robotRepository,
                        patrolMapRepository,
                        navigationWaypointService,
                        detectedEventRepository,
                        patrolCheckpointVisitRecorder));
    }

    private void stubSingleDestination() {
        when(patrolMapRepository.findForUpdateByApartmentComplexId(2L))
                .thenReturn(Optional.of(patrolMap));
        when(navigationWaypointService.requireValidCurrentRoute(patrolMap))
                .thenReturn(List.of(destinationWaypoint));
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
