package com.oneloop.event.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "event_evidence")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class EventEvidence extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "evidence_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "event_id", nullable = false)
    private DetectedEvent event;

    @Enumerated(EnumType.STRING)
    @Column(name = "media_type", nullable = false, length = 20)
    private MediaType mediaType;

    @Column(name = "file_url", nullable = false, length = 1000)
    private String fileUrl;

    @Column(name = "captured_at")
    private LocalDateTime capturedAt;

    public EventEvidence(
            DetectedEvent event, MediaType mediaType, String fileUrl, LocalDateTime capturedAt) {
        this.event = event;
        this.mediaType = mediaType;
        this.fileUrl = fileUrl;
        this.capturedAt = capturedAt;
    }
}
