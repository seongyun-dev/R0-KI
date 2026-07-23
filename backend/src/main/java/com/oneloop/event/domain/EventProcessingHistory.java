package com.oneloop.event.domain;

import com.oneloop.global.common.BaseEntity;
import com.oneloop.member.domain.Member;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "event_processing_history")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class EventProcessingHistory extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "processing_history_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "event_id", nullable = false)
    private DetectedEvent event;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "processing_member_id")
    private Member processingMember;

    @Enumerated(EnumType.STRING)
    @Column(name = "changed_processing_status", nullable = false, length = 20)
    private ProcessingStatus changedStatus;

    @Column(name = "processing_note", length = 500)
    private String note;

    @Column(name = "changed_at", nullable = false)
    private LocalDateTime changedAt;

    public EventProcessingHistory(
            DetectedEvent event,
            Member processingMember,
            ProcessingStatus changedStatus,
            String note) {
        this.event = event;
        this.processingMember = processingMember;
        this.changedStatus = changedStatus;
        this.note = note;
        this.changedAt = LocalDateTime.now();
    }
}
