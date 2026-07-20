package com.oneloop.resident.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "registered_vehicles")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class RegisteredVehicle extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "vehicle_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "resident_id", nullable = false)
    private Resident resident;

    @Column(name = "license_plate", nullable = false, unique = true, length = 20)
    private String licensePlate;

    @Column(name = "disabled_vehicle", nullable = false)
    private boolean disabledVehicle;

    public RegisteredVehicle(Resident resident, String licensePlate, boolean disabledVehicle) {
        this.resident = resident;
        this.licensePlate = licensePlate;
        this.disabledVehicle = disabledVehicle;
    }
}
