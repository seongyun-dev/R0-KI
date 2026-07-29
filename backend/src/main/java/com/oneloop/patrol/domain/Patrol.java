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

    // 백엔드가 발행한 MQTT 명령의 UUID이며 IoT ACK 검증에 사용한다.
    @Column(name = "command_id", unique = true, length = 36)
    private String commandId;

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

    public Patrol(PatrolRobot robot, LocalDateTime startedAt, String commandId) {
        this.robot = robot;
        this.startedAt = startedAt;
        this.commandId = commandId;
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


    // START_PATROL 명령이 거절/실패한 경우에만 호출되며, 아직 순찰이 시작되지 않았으므로 배터리/기간은 남기지 않는다.
    public void fail() {
        this.status = PatrolStatus.FAILED;
        this.endedAt = LocalDateTime.now();
    }

    // STOP_PATROL 발행 시 commandId를 새로 발급한 값으로 교체한다(START_PATROL의 commandId는 이미 ACK 처리가 끝난 상태).
    public void updateCommandId(String commandId) {
        this.commandId = commandId;
    }
}
