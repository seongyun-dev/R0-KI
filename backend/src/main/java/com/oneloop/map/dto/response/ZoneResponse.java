package com.oneloop.map.dto.response;

import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import java.math.BigDecimal;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class ZoneResponse {

    private Long zoneId;
    private String name;
    private CheckpointType type;
    private BigDecimal minX;
    private BigDecimal minY;
    private BigDecimal maxX;
    private BigDecimal maxY;

    public static ZoneResponse from(Checkpoint checkpoint) {
        return ZoneResponse.builder()
                .zoneId(checkpoint.getId())
                .name(checkpoint.getName())
                .type(checkpoint.getType())
                .minX(checkpoint.getMinX())
                .minY(checkpoint.getMinY())
                .maxX(checkpoint.getMaxX())
                .maxY(checkpoint.getMaxY())
                .build();
    }
}
