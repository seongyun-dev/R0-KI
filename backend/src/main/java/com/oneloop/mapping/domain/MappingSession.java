package com.oneloop.mapping.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import com.oneloop.robot.domain.PatrolRobot;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(name = "mapping_sessions")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MappingSession extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "mapping_session_id")
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false, unique = true)
    private ApartmentComplex apartmentComplex;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "robot_id", nullable = false, unique = true)
    private PatrolRobot robot;

    // 백엔드가 발행한 MQTT 명령의 UUID이며 IoT ACK 검증에 사용한다.
    @Column(name = "command_id", nullable = false, unique = true, length = 36)
    private String commandId;

    // 세션 생성 직후에는 로봇이 실제 매핑을 시작하기 전이므로 REQUESTED 상태다.
    @Enumerated(EnumType.STRING)
    @Column(name = "mapping_status", nullable = false, length = 20)
    private MappingStatus status = MappingStatus.REQUESTED;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "finished_at")
    private LocalDateTime finishedAt;

    public MappingSession(ApartmentComplex apartmentComplex, PatrolRobot robot, String commandId) {
        this.apartmentComplex = apartmentComplex;
        this.robot = robot;
        this.commandId = commandId;
    }

    public void fail() {
        // 명령 거절 등으로 세션이 종료된 시각을 함께 기록한다.
        status = MappingStatus.FAILED;
        finishedAt = LocalDateTime.now();
    }

    public void startMapping() {
        // IoT가 실제 SLAM 시작 상태를 전송한 시점에만 시작 시각을 기록한다.
        status = MappingStatus.MAPPING;
        startedAt = LocalDateTime.now();
    }

    public void complete() {
        status = MappingStatus.COMPLETED;
        finishedAt = LocalDateTime.now();
    }

    public void restart(String newCommandId) {
        if (status == MappingStatus.REQUESTED || status == MappingStatus.MAPPING) {
            throw new IllegalStateException("진행 중인 지도 생성 세션은 다시 시작할 수 없습니다.");
        }
        commandId = newCommandId;
        status = MappingStatus.REQUESTED;
        startedAt = null;
        finishedAt = null;
    }
}
