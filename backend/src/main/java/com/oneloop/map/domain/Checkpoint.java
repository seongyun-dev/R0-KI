package com.oneloop.map.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import java.math.BigDecimal;
import lombok.*;

@Getter
@Entity
@Table(name = "checkpoints")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Checkpoint extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "checkpoint_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "map_id", nullable = false)
    private PatrolMap patrolMap;

    @Enumerated(EnumType.STRING)
    @Column(name = "checkpoint_type", nullable = false, length = 30)
    private CheckpointType type;

    @Column(name = "checkpoint_name", nullable = false, length = 100)
    private String name;

    @Column(name = "min_x", nullable = false, precision = 10, scale = 3)
    private BigDecimal minX;

    @Column(name = "min_y", nullable = false, precision = 10, scale = 3)
    private BigDecimal minY;

    @Column(name = "max_x", nullable = false, precision = 10, scale = 3)
    private BigDecimal maxX;

    @Column(name = "max_y", nullable = false, precision = 10, scale = 3)
    private BigDecimal maxY;

    @Column(name = "active", nullable = false)
    private boolean active = true;

    public Checkpoint(
            PatrolMap patrolMap,
            CheckpointType type,
            String name,
            BigDecimal minX,
            BigDecimal minY,
            BigDecimal maxX,
            BigDecimal maxY) {
        this.patrolMap = patrolMap;
        this.type = type;
        this.name = name;
        this.minX = minX;
        this.minY = minY;
        this.maxX = maxX;
        this.maxY = maxY;
        this.active = true;
    }
}
