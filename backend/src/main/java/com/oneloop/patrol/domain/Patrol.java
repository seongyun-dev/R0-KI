package com.oneloop.patrol.domain;

import com.oneloop.global.common.BaseEntity;
import com.oneloop.map.domain.PatrolMap;
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

    // 순찰 시작 시점의 맵 스냅샷. 레거시 행은 null 일 수 있다.
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "map_id")
    private PatrolMap map;

    @Column(name = "map_version")
    private Integer mapVersion;

    @Enumerated(EnumType.STRING)
    @Column(name = "patrol_status", nullable = false, length = 20)
    private PatrolStatus status = PatrolStatus.IN_PROGRESS;

    // 백엔드가 발행한 MQTT 명령의 UUID이며 IoT ACK 검증에 사용한다.
    @Column(name = "command_id", unique = true, length = 36)
    private String commandId;

    // true면 DESTINATION 도착으로 발행한 STOP이며 성공 ACK 뒤 COMPLETED로 확정한다.
    @Column(name = "completion_requested", nullable = false)
    private boolean completionRequested;

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

    public Patrol(
            PatrolRobot robot, PatrolMap map, LocalDateTime startedAt, String commandId) {
        this(robot, startedAt, commandId);
        bindMap(map);
    }

    public void bindMap(PatrolMap map) {
        if (map == null) {
            this.map = null;
            this.mapVersion = null;
            return;
        }
        this.map = map;
        this.mapVersion = map.getMapVersion();
    }

    public void increaseDetectedEventCount() {
        this.detectedEventCount++;
    }

    public void complete() {
        finish(PatrolStatus.COMPLETED);
    }

    public void requestStop(String commandId) {
        if (status != PatrolStatus.IN_PROGRESS && status != PatrolStatus.STOP_REQUESTED) {
            throw new IllegalStateException("진행 중이거나 종료 요청 중인 순찰만 종료 요청할 수 있습니다.");
        }
        // MQTT 발행만으로 실제 정지를 확정할 수 없으므로, 성공 ACK 전까지 중간 상태로 둔다.
        // 재요청할 때는 최신 commandId로 교체하여 늦게 도착한 이전 ACK가 상태를 바꾸지 못하게 한다.
        this.status = PatrolStatus.STOP_REQUESTED;
        this.commandId = commandId;
        this.completionRequested = false;
    }

    public void requestCompletion(String commandId) {
        if (status != PatrolStatus.IN_PROGRESS) {
            throw new IllegalStateException("진행 중인 순찰만 완료 요청할 수 있습니다.");
        }
        this.status = PatrolStatus.STOP_REQUESTED;
        this.commandId = commandId;
        this.completionRequested = true;
    }

    public void stop() {
        if (status != PatrolStatus.STOP_REQUESTED || completionRequested) {
            throw new IllegalStateException("종료 요청 중인 순찰만 종료할 수 있습니다.");
        }
        finish(PatrolStatus.STOPPED);
    }

    public void completeRequested() {
        if (status != PatrolStatus.STOP_REQUESTED || !completionRequested) {
            throw new IllegalStateException("완료 요청 중인 순찰만 완료할 수 있습니다.");
        }
        finish(PatrolStatus.COMPLETED);
    }

    public void retryCompletionAfterFailedStop() {
        if (status != PatrolStatus.STOP_REQUESTED || !completionRequested) {
            throw new IllegalStateException("완료 요청 중인 순찰만 완료 재시도할 수 있습니다.");
        }
        // 실패한 commandId는 그대로 두어 중복 ACK를 식별한다. 다음 pose가 도착을
        // 재확인하면 requestCompletion()이 새 commandId로 교체한다.
        this.status = PatrolStatus.IN_PROGRESS;
        this.completionRequested = false;
    }

    private void finish(PatrolStatus finishedStatus) {
        this.status = finishedStatus;
        this.completionRequested = false;
        this.endedAt = LocalDateTime.now();
        this.endBatteryLevel = robot.getBatteryLevel();
        if (startedAt != null)
            this.totalDuration = Math.toIntExact(Duration.between(startedAt, endedAt).toSeconds());
    }

    // START_PATROL 명령이 거절/실패한 경우에만 호출되며, 아직 순찰이 시작되지 않았으므로 배터리/기간은 남기지 않는다.
    public void fail() {
        // 통신 단절로 끝난 순찰도 보고서에 종료 시점과 운행 시간을 남길 수 있도록 종료 정보를 채운다.
        this.status = PatrolStatus.FAILED;
        this.completionRequested = false;
        this.endedAt = LocalDateTime.now();
        this.endBatteryLevel = robot.getBatteryLevel();
        if (startedAt != null)
            this.totalDuration = Math.toIntExact(Duration.between(startedAt, endedAt).toSeconds());
    }

    // STOP_PATROL 발행 시 commandId를 새로 발급한 값으로 교체한다(START_PATROL의 commandId는 이미 ACK 처리가 끝난 상태).
    public void updateCommandId(String commandId) {
        this.commandId = commandId;
    }
}
