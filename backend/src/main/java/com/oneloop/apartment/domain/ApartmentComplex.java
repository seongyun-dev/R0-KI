package com.oneloop.apartment.domain;

import com.oneloop.global.common.BaseEntity;
import com.oneloop.map.domain.PatrolMap;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

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

    // 단지에서 현재 운영에 쓰는 맵. null 이면 아직 맵이 없다.
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "active_map_id")
    private PatrolMap activeMap;

    public ApartmentComplex(String name, String address, String postalCode) {
        this.name = name;
        this.address = address;
        this.postalCode = postalCode;
    }

    public void assignActiveMap(PatrolMap map) {
        this.activeMap = map;
    }

    public void clearActiveMap() {
        this.activeMap = null;
    }
}
