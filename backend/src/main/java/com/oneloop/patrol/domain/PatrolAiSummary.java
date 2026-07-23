package com.oneloop.patrol.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "patrol_ai_summaries")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolAiSummary extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "ai_summary_id")
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "patrol_id", nullable = false, unique = true)
    private Patrol patrol;

    @Enumerated(EnumType.STRING)
    @Column(name = "generation_status", nullable = false, length = 20)
    private AiSummaryGenerationStatus generationStatus = AiSummaryGenerationStatus.PENDING;

    @Column(name = "summary_content", columnDefinition = "TEXT")
    private String summaryContent;

    public PatrolAiSummary(Patrol patrol) {
        this.patrol = patrol;
    }

    public void startGeneration() {
        this.generationStatus = AiSummaryGenerationStatus.PROCESSING;
    }

    public void completeGeneration(String summaryContent) {
        this.generationStatus = AiSummaryGenerationStatus.COMPLETED;
        this.summaryContent = summaryContent;
    }

    public void failGeneration() {
        this.generationStatus = AiSummaryGenerationStatus.FAILED;
    }
}
