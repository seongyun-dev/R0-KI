package com.oneloop.patrol.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "route_positions")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class RoutePosition extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "position_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "patrol_id", nullable = false)
    private Patrol patrol;

    @Column(name = "x_coordinate", nullable = false, precision = 10, scale = 3)
    private BigDecimal x;

    @Column(name = "y_coordinate", nullable = false, precision = 10, scale = 3)
    private BigDecimal y;

    @Column(name = "recorded_at", nullable = false)
    private LocalDateTime recordedAt;

    public RoutePosition(Patrol patrol, BigDecimal x, BigDecimal y, LocalDateTime recordedAt) {
        this.patrol = patrol;
        this.x = x;
        this.y = y;
        this.recordedAt = recordedAt;
    }
}
