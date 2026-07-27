package com.oneloop.mapping.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import com.oneloop.robot.domain.PatrolRobot;
import jakarta.persistence.*;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "robot_id", nullable = false)
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
}
