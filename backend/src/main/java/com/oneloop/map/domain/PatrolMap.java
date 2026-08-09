package com.oneloop.map.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "patrol_maps")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolMap extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "map_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @Column(name = "map_name", nullable = false, length = 255)
    private String name;

    @Column(name = "map_url", nullable = false, length = 1000)
    private String url;

    public PatrolMap(ApartmentComplex apartmentComplex, String name, String url) {
        this.apartmentComplex = apartmentComplex;
        this.name = name;
        this.url = url;
    }
}
