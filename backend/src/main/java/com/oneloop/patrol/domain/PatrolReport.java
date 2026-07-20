package com.oneloop.patrol.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "patrol_reports")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolReport extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "report_id")
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "patrol_id", nullable = false, unique = true)
    private Patrol patrol;

    @Column(name = "report_title", nullable = false, length = 200)
    private String title;

    @Column(name = "patrol_summary", columnDefinition = "TEXT")
    private String summary;

    @Column(name = "report_content", columnDefinition = "TEXT")
    private String content;

    @Column(name = "total_event_count", nullable = false)
    private int totalEventCount;

    @Column(name = "emergency_event_count", nullable = false)
    private int emergencyEventCount;

    public PatrolReport(
            Patrol patrol,
            String title,
            String summary,
            String content,
            int totalEventCount,
            int emergencyEventCount) {
        this.patrol = patrol;
        this.title = title;
        this.summary = summary;
        this.content = content;
        this.totalEventCount = totalEventCount;
        this.emergencyEventCount = emergencyEventCount;
    }
}
