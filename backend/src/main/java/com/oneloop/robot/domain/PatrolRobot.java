package com.oneloop.robot.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "patrol_robots")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolRobot extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "robot_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @Column(name = "robot_name", nullable = false, length = 100)
    private String name;

    @Column(name = "robot_serial_number", nullable = false, unique = true, length = 100)
    private String serialNumber;

    @Column(name = "service_token", unique = true, length = 255)
    private String serviceToken;

    @Column(name = "x_coordinate", precision = 10, scale = 3)
    private BigDecimal xCoordinate;

    @Column(name = "y_coordinate", precision = 10, scale = 3)
    private BigDecimal yCoordinate;

    @Column(name = "heading", precision = 6, scale = 2)
    private BigDecimal heading;

    @Column(name = "location_updated_at")
    private LocalDateTime locationUpdatedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "robot_status", nullable = false, length = 20)
    private RobotStatus status = RobotStatus.IDLE;

    @Column(name = "battery_level", precision = 5, scale = 2)
    private BigDecimal batteryLevel;

    @Enumerated(EnumType.STRING)
    @Column(name = "camera_status", length = 20)
    private SensorStatus cameraStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "lidar_status", length = 20)
    private SensorStatus lidarStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "motor_status", length = 20)
    private SensorStatus motorStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "line_sensor_status", length = 20)
    private SensorStatus lineSensorStatus;

    @Column(name = "status_reported_at")
    private LocalDateTime statusReportedAt;

    @Column(name = "last_connected_at")
    private LocalDateTime lastConnectedAt;

    // obstacle.status=STOP일 때만 값이 채워지고, 해제되면 둘 다 null로 비워짐
    @Column(name = "obstacle_direction", length = 20)
    private String obstacleDirection;

    @Column(name = "obstacle_message", length = 255)
    private String obstacleMessage;

    public PatrolRobot(ApartmentComplex apartmentComplex, String name, String serialNumber) {
        this.apartmentComplex = apartmentComplex;
        this.name = name;
        this.serialNumber = serialNumber;
    }

    // pose 토픽 수신 시 호출
    public void updatePose(BigDecimal x, BigDecimal y, BigDecimal heading, LocalDateTime locationUpdatedAt) {
        this.xCoordinate = x;
        this.yCoordinate = y;
        this.heading = heading;
        this.locationUpdatedAt = locationUpdatedAt;
        this.lastConnectedAt = locationUpdatedAt;
    }

    // status 토픽 수신 시 호출 - obstacleDirection/obstacleMessage는 장애물 상태가 아니면 null
    public void updateStatus(
            RobotStatus status,
            BigDecimal batteryLevel,
            SensorStatus cameraStatus,
            SensorStatus lidarStatus,
            SensorStatus motorStatus,
            SensorStatus lineSensorStatus,
            LocalDateTime statusReportedAt,
            String obstacleDirection,
            String obstacleMessage) {
        this.status = status;
        this.batteryLevel = batteryLevel;
        this.cameraStatus = cameraStatus;
        this.lidarStatus = lidarStatus;
        this.motorStatus = motorStatus;
        this.lineSensorStatus = lineSensorStatus;
        this.statusReportedAt = statusReportedAt;
        this.lastConnectedAt = statusReportedAt;
        this.obstacleDirection = obstacleDirection;
        this.obstacleMessage = obstacleMessage;
    }

    public void rename(String name) {
        this.name = name;
    }

    public void delete() {
        this.status = RobotStatus.DELETED;
    }

    public void issueServiceToken(String serviceToken) {
        this.serviceToken = serviceToken;
    }
}
