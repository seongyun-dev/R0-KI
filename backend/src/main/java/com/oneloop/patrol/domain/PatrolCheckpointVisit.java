package com.oneloop.patrol.domain;

import com.oneloop.map.domain.Checkpoint;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
        name = "patrol_checkpoint_visits",
        uniqueConstraints =
                @UniqueConstraint(
                        name = "uk_patrol_checkpoint_visits_patrol_sequence",
                        columnNames = {"patrol_id", "visit_sequence"}))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolCheckpointVisit {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "visit_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "patrol_id", nullable = false)
    private Patrol patrol;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "checkpoint_id", nullable = false)
    private Checkpoint checkpoint;

    @Column(name = "visit_sequence", nullable = false)
    private int visitSequence;

    @Column(name = "visited_at", nullable = false)
    private LocalDateTime visitedAt;

    public PatrolCheckpointVisit(
            Patrol patrol, Checkpoint checkpoint, int visitSequence, LocalDateTime visitedAt) {
        this.patrol = patrol;
        this.checkpoint = checkpoint;
        this.visitSequence = visitSequence;
        this.visitedAt = visitedAt;
    }
}
