package com.oneloop.map.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import java.math.BigDecimal;
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

    @Column(name = "resolution", precision = 6, scale = 4)
    private BigDecimal resolution;

    @Column(name = "origin_x", precision = 10, scale = 3)
    private BigDecimal originX;

    @Column(name = "origin_y", precision = 10, scale = 3)
    private BigDecimal originY;

    @Column(name = "origin_yaw", precision = 6, scale = 2)
    private BigDecimal originYaw;

    @Column(name = "width")
    private Integer width;

    @Column(name = "height")
    private Integer height;

    @Column(name = "map_version")
    private Integer mapVersion = 1;

    public PatrolMap(ApartmentComplex apartmentComplex, String name, String url) {
        this.apartmentComplex = apartmentComplex;
        this.name = name;
        this.url = url;
    }
}
