package com.oneloop.robot.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.*;

@Getter
@Entity
@Table(name = "patrol_robots")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolRobot extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "robot_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @Column(name = "robot_name", nullable = false, length = 100)
    private String name;

    @Column(name = "robot_serial_number", nullable = false, unique = true, length = 100)
    private String serialNumber;

    @Column(name = "x_coordinate", precision = 10, scale = 3)
    private BigDecimal xCoordinate;

    @Column(name = "y_coordinate", precision = 10, scale = 3)
    private BigDecimal yCoordinate;

    @Column(name = "location_updated_at")
    private LocalDateTime locationUpdatedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "robot_status", nullable = false, length = 20)
    private RobotStatus status = RobotStatus.IDLE;

    @Column(name = "battery_level", precision = 5, scale = 2)
    private BigDecimal batteryLevel;

    @Column(name = "last_connected_at")
    private LocalDateTime lastConnectedAt;

    public PatrolRobot(ApartmentComplex apartmentComplex, String name, String serialNumber) {
        this.apartmentComplex = apartmentComplex;
        this.name = name;
        this.serialNumber = serialNumber;
    }

    public void updateLocation(BigDecimal x, BigDecimal y, BigDecimal batteryLevel) {
        this.xCoordinate = x;
        this.yCoordinate = y;
        this.batteryLevel = batteryLevel;
        this.locationUpdatedAt = LocalDateTime.now();
        this.lastConnectedAt = LocalDateTime.now();
    }

    public void changeStatus(RobotStatus status) {
        this.status = status;
    }
}
