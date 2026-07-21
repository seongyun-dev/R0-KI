package com.oneloop.resident.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "residents")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Resident extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "resident_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(name = "phone_number", nullable = false, length = 20)
    private String phoneNumber;

    @Column(name = "building_number", nullable = false, length = 20)
    private String buildingNumber;

    @Column(name = "unit_number", nullable = false, length = 20)
    private String unitNumber;

    @Column(name = "kakao_notification_enabled", nullable = false)
    private boolean kakaoNotificationEnabled = true;

    public Resident(
            ApartmentComplex apartmentComplex,
            String name,
            String phoneNumber,
            String buildingNumber,
            String unitNumber) {
        this.apartmentComplex = apartmentComplex;
        this.name = name;
        this.phoneNumber = phoneNumber;
        this.buildingNumber = buildingNumber;
        this.unitNumber = unitNumber;
    }

    public void changeKakaoNotification(boolean enabled) {
        this.kakaoNotificationEnabled = enabled;
    }
}
