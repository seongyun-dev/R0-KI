package com.oneloop.robot.service;

import com.oneloop.patrol.service.PatrolCommandService;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.domain.RoutePosition;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.patrol.repository.RoutePositionRepository;
import com.oneloop.robot.domain.ObstacleStatus;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.dto.mqtt.RobotPoseMessage;
import com.oneloop.robot.dto.mqtt.RobotStatusMessage;
import com.oneloop.robot.event.RobotLocationUpdatedEvent;
import com.oneloop.robot.event.RobotObstacleEvent;
import com.oneloop.robot.event.RobotStatusUpdatedEvent;
import com.oneloop.robot.repository.RobotRepository;
import java.time.LocalDateTime;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// MQTT로 수신한 로봇 위치(pose)·상태(status) 메시지를 PatrolRobot 엔티티에 반영한다.
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RobotTelemetryService {

    private static final int SUPPORTED_SCHEMA_VERSION = 1;

    private final RobotRepository robotRepository;
    private final PatrolRepository patrolRepository;
    private final RoutePositionRepository routePositionRepository;
    private final ApplicationEventPublisher eventPublisher;
    private final PatrolCommandService patrolCommandService;

    // pose 메시지 처리 진입점 - robotKey로 로봇을 찾아 좌표를 갱신하고, 도착지 도달 여부를 확인해 순찰 자동 종료를 시도한다.
    @Transactional
    public void updatePose(RobotPoseMessage message) {
        if (!isValid(message)) {
            log.warn("[MQTT] 잘못된 pose 메시지를 무시합니다. message={}", message);
            return;
        }

        robotRepository
                .findBySerialNumber(message.robotKey())
                .ifPresentOrElse(
                        robot -> applyPose(robot, message),
                        () -> log.warn("[MQTT] 알 수 없는 robotKey={}, pose 갱신 무시", message.robotKey()));
    }

    private void applyPose(PatrolRobot robot, RobotPoseMessage message) {
        LocalDateTime reportedAt = message.timestamp().toLocalDateTime();
        robot.updatePose(message.x(), message.y(), message.heading(), reportedAt);

        // pose는 1초마다 지도 마커를 움직이는 용도로 사용하고, 영구 경로 저장은 status 수신 시 처리합니다.
        publishLocationUpdated(robot);

        // 최신 위치 반영 후 도착지 도달 여부를 확인해 진행 중인 순찰의 자동 종료를 시도합니다.
        patrolCommandService.autoCompleteIfArrived(robot, message.x(), message.y());
    }

    // status 메시지 처리 진입점 - robotKey로 로봇을 찾아 applyStatus로 위임
    @Transactional
    public void updateStatus(RobotStatusMessage message) {
        if (!isValid(message)) {
            log.warn("[MQTT] 잘못된 status 메시지를 무시합니다. message={}", message);
            return;
        }

        LocalDateTime receivedAt = LocalDateTime.now();

        robotRepository
                .findBySerialNumber(message.robotKey())
                .ifPresentOrElse(
                        robot -> applyStatus(robot, message, receivedAt),
                        () -> log.warn("[MQTT] 알 수 없는 robotKey={}, status 갱신 무시", message.robotKey()));
    }

    // obstacle.status=STOP이면 기기가 보낸 state 필드보다 우선해서 robot_status를 OBSTACLE_STOP으로 덮어씀
    private void applyStatus(
            PatrolRobot robot, RobotStatusMessage message, LocalDateTime receivedAt) {
        boolean obstacleStop =
                message.obstacle() != null && message.obstacle().status() == ObstacleStatus.STOP;
        RobotStatus previousStatus = robot.getStatus();
        RobotStatus resolvedStatus = obstacleStop ? RobotStatus.OBSTACLE_STOP : message.state();
        String direction = obstacleStop ? message.obstacle().direction() : null;
        String reason = obstacleStop ? message.obstacle().reasonMessage() : null;
        LocalDateTime reportedAt = message.timestamp().toLocalDateTime();

        robot.updateStatus(
                resolvedStatus,
                message.battery(),
                message.camera(),
                message.lidar(),
                message.motor(),
                message.lineSensor(),
                reportedAt,
                direction,
                reason);
        robot.recordConnection(receivedAt);

        if (previousStatus == RobotStatus.OFFLINE && isPatrolling(resolvedStatus)) {
            // 재연결 메시지가 아직 주행 중이라고 알려주면 IDLE로 덮어쓰지 않고 실제 STOP_PATROL을 보낸다.
            patrolCommandService.stopAfterReconnect(robot);
        }

        // status heartbeat가 약 5초 주기이므로 그 시점의 최신 pose를 순찰 경로로 저장합니다.
        saveRoutePosition(robot);
        publishObstacleTransition(robot.getId(), previousStatus, resolvedStatus, direction, reason);
        publishStatusUpdated(robot);
    }

    private boolean isPatrolling(RobotStatus status) {
        return status == RobotStatus.PATROLLING || status == RobotStatus.OBSTACLE_STOP;
    }

    private void saveRoutePosition(PatrolRobot robot) {
        if (!isPatrolling(robot.getStatus())
                || robot.getXCoordinate() == null
                || robot.getYCoordinate() == null
                || robot.getLocationUpdatedAt() == null) {
            return;
        }

        patrolRepository
                .findFirstByRobotIdAndStatusOrderByStartedAtDesc(
                        robot.getId(), PatrolStatus.IN_PROGRESS)
                .ifPresent(
                        patrol ->
                                routePositionRepository.save(
                                        new RoutePosition(
                                                patrol,
                                                robot.getXCoordinate(),
                                                robot.getYCoordinate(),
                                                robot.getLocationUpdatedAt())));
    }

    private void publishLocationUpdated(PatrolRobot robot) {
        eventPublisher.publishEvent(RobotLocationUpdatedEvent.from(robot));
    }

    private void publishStatusUpdated(PatrolRobot robot) {
        eventPublisher.publishEvent(
                new RobotStatusUpdatedEvent(
                        robot.getApartmentComplex().getId(),
                        robot.getId(),
                        robot.getStatus(),
                        robot.getBatteryLevel(),
                        robot.getStatusReportedAt()));
    }

    // 매 heartbeat(5초)마다 이벤트를 쏘지 않도록, OBSTACLE_STOP으로 전환되거나 벗어나는 순간에만 발행
    private void publishObstacleTransition(
            Long robotId, RobotStatus previous, RobotStatus resolved, String direction, String reason) {
        if (resolved == RobotStatus.OBSTACLE_STOP && previous != RobotStatus.OBSTACLE_STOP) {
            eventPublisher.publishEvent(
                    new RobotObstacleEvent(robotId, ObstacleStatus.STOP, direction, reason));
        } else if (resolved != RobotStatus.OBSTACLE_STOP && previous == RobotStatus.OBSTACLE_STOP) {
            eventPublisher.publishEvent(new RobotObstacleEvent(robotId, ObstacleStatus.CLEAR, null, null));
        }
    }

    // 지원 버전 + 필수 필드(robotKey/x/y/timestamp) 존재 여부만 확인
    private boolean isValid(RobotPoseMessage message) {
        return message.schemaVersion() == SUPPORTED_SCHEMA_VERSION
                && message.robotKey() != null
                && message.x() != null
                && message.y() != null
                && message.timestamp() != null;
    }

    // 지원 버전 + 필수 필드(robotKey/state/timestamp) 존재 여부만 확인
    private boolean isValid(RobotStatusMessage message) {
        return message.schemaVersion() == SUPPORTED_SCHEMA_VERSION
                && message.robotKey() != null
                && message.state() != null
                && message.timestamp() != null;
    }
}
