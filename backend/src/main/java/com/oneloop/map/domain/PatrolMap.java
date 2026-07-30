package com.oneloop.map.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(name = "patrol_maps")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class PatrolMap extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "map_id")
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false, unique = true)
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

    public PatrolMap(
            ApartmentComplex apartmentComplex,
            String name,
            String url,
            BigDecimal resolution,
            BigDecimal originX,
            BigDecimal originY,
            BigDecimal originYaw,
            Integer width,
            Integer height) {
        this.apartmentComplex = apartmentComplex;
        this.name = name;
        this.url = url;
        this.resolution = resolution;
        this.originX = originX;
        this.originY = originY;
        this.originYaw = originYaw;
        this.width = width;
        this.height = height;
        this.mapVersion = 1;
    }

    public void update(
            String name,
            String url,
            BigDecimal resolution,
            BigDecimal originX,
            BigDecimal originY,
            BigDecimal originYaw,
            Integer width,
            Integer height) {
        this.name = name;
        this.url = url;
        this.resolution = resolution;
        this.originX = originX;
        this.originY = originY;
        this.originYaw = originYaw;
        this.width = width;
        this.height = height;
        this.mapVersion = mapVersion == null ? 1 : mapVersion + 1;
    }
}
