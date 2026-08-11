package com.oneloop.map.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
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

    // 단지당 맵을 여러 장 둘 수 있다. active 는 ApartmentComplex.activeMap 이 가리킨다.
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

    @Enumerated(EnumType.STRING)
    @Column(name = "map_status", nullable = false, length = 20)
    private MapStatus status = MapStatus.ACTIVE;

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
        this.status = MapStatus.ACTIVE;
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

    public void activate() {
        this.status = MapStatus.ACTIVE;
    }

    public void archive() {
        this.status = MapStatus.ARCHIVED;
    }

    public boolean isActive() {
        return status == MapStatus.ACTIVE;
    }
}
