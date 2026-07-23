package com.oneloop.patrol.domain;

import com.oneloop.global.common.BaseEntity;
import com.oneloop.robot.domain.PatrolRobot;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "patrols")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Patrol extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "patrol_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "robot_id", nullable = false)
    private PatrolRobot robot;

    @Enumerated(EnumType.STRING)
    @Column(name = "patrol_status", nullable = false, length = 20)
    private PatrolStatus status = PatrolStatus.IN_PROGRESS;

    @Column(name = "patrol_started_at")
    private LocalDateTime startedAt;

    @Column(name = "patrol_ended_at")
    private LocalDateTime endedAt;

    @Column(name = "total_duration")
    private Integer totalDuration;

    @Column(name = "detected_event_count", nullable = false)
    private int detectedEventCount;

    @Column(name = "start_battery_level", precision = 5, scale = 2)
    private BigDecimal startBatteryLevel;

    @Column(name = "end_battery_level", precision = 5, scale = 2)
    private BigDecimal endBatteryLevel;

    public Patrol(PatrolRobot robot, LocalDateTime startedAt) {
        this.robot = robot;
        this.startedAt = startedAt;
        this.startBatteryLevel = robot.getBatteryLevel();
    }

    public void increaseDetectedEventCount() {
        this.detectedEventCount++;
    }

    public void complete() {
        this.status = PatrolStatus.COMPLETED;
        this.endedAt = LocalDateTime.now();
        this.endBatteryLevel = robot.getBatteryLevel();
        if (startedAt != null)
            this.totalDuration = Math.toIntExact(Duration.between(startedAt, endedAt).toSeconds());
    }
}
