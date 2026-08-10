package com.oneloop.apartment.domain;

import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "apartment_complexes")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ApartmentComplex extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "apartment_complex_id")
    private Long id;

    @Column(name = "apartment_name", nullable = false, length = 100)
    private String name;

    @Column(nullable = false, length = 200)
    private String address;

    @Column(name = "postal_code", length = 10)
    private String postalCode;

    public ApartmentComplex(String name, String address, String postalCode) {
        this.name = name;
        this.address = address;
        this.postalCode = postalCode;
    }
}
