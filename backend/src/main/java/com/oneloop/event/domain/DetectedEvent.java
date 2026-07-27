package com.oneloop.event.domain;

import com.oneloop.global.common.BaseEntity;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.robot.domain.PatrolRobot;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "detected_events")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class DetectedEvent extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "event_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "patrol_id")
    private Patrol patrol;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "robot_id", nullable = false)
    private PatrolRobot robot;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false, length = 30)
    private EventType type;

    @Column(name = "event_title", nullable = false, length = 200)
    private String title;

    @Column(name = "event_details", columnDefinition = "TEXT")
    private String details;

    @Column(name = "confidence", precision = 4, scale = 3)
    private BigDecimal confidence;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @Column(name = "x_coordinate", precision = 10, scale = 3)
    private BigDecimal x;

    @Column(name = "y_coordinate", precision = 10, scale = 3)
    private BigDecimal y;

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level", nullable = false, length = 20)
    private RiskLevel riskLevel;

    @Enumerated(EnumType.STRING)
    @Column(name = "processing_status", nullable = false, length = 20)
    private ProcessingStatus processingStatus = ProcessingStatus.DETECTED;

    @Column(name = "processed_at")
    private LocalDateTime processedAt;

    @Column(name = "recognized_license_plate", length = 20)
    private String recognizedLicensePlate;

    public DetectedEvent(
            Patrol patrol,
            PatrolRobot robot,
            EventType type,
            String title,
            String details,
            BigDecimal confidence,
            LocalDateTime occurredAt,
            BigDecimal x,
            BigDecimal y,
            RiskLevel riskLevel,
            String recognizedLicensePlate) {
        this.patrol = patrol;
        this.robot = robot;
        this.type = type;
        this.title = title;
        this.details = details;
        this.confidence = confidence;
        this.occurredAt = occurredAt;
        this.x = x;
        this.y = y;
        this.riskLevel = riskLevel;
        this.recognizedLicensePlate = recognizedLicensePlate;
    }

    public void startProcessing() {
        this.processingStatus = ProcessingStatus.PROCESSING;
    }

    public void completeProcessing() {
        this.processingStatus = ProcessingStatus.COMPLETED;
        this.processedAt = LocalDateTime.now();
    }
}
