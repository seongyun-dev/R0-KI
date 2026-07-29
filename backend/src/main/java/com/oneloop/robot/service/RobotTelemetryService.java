package com.oneloop.robot.service;

import com.oneloop.patrol.service.PatrolCommandService;
import com.oneloop.robot.domain.ObstacleStatus;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.dto.mqtt.RobotPoseMessage;
import com.oneloop.robot.dto.mqtt.RobotStatusMessage;
import com.oneloop.robot.event.RobotObstacleEvent;
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
                        robot -> {
                            robot.updatePose(
                                    message.x(),
                                    message.y(),
                                    message.heading(),
                                    message.timestamp().toLocalDateTime());
                            // 도착지 도달 여부를 확인해 순찰 자동 종료를 시도
                            patrolCommandService.autoCompleteIfArrived(robot, message.x(), message.y());
                        },
                        () -> log.warn("[MQTT] 알 수 없는 robotKey={}, pose 갱신 무시", message.robotKey()));
    }

    // status 메시지 처리 진입점 - robotKey로 로봇을 찾아 applyStatus로 위임
    @Transactional
    public void updateStatus(RobotStatusMessage message) {
        if (!isValid(message)) {
            log.warn("[MQTT] 잘못된 status 메시지를 무시합니다. message={}", message);
            return;
        }

        robotRepository
                .findBySerialNumber(message.robotKey())
                .ifPresentOrElse(
                        robot -> applyStatus(robot, message),
                        () -> log.warn("[MQTT] 알 수 없는 robotKey={}, status 갱신 무시", message.robotKey()));
    }

    // obstacle.status=STOP이면 기기가 보낸 state 필드보다 우선해서 robot_status를 OBSTACLE_STOP으로 덮어씀
    private void applyStatus(PatrolRobot robot, RobotStatusMessage message) {
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

        publishObstacleTransition(robot.getId(), previousStatus, resolvedStatus, direction, reason);
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
