package com.oneloop.map.dto.response;

import com.oneloop.map.domain.PatrolMap;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "SLAM 지도 등록 응답")
@Getter
@Builder
public class MapUploadResponse {

    private Long mappingSessionId;
    private Long mapId;
    private String mapUrl;
    private Integer mapVersion;
    private MappingStatus mappingStatus;
    private LocalDateTime completedAt;

    public static MapUploadResponse from(MappingSession session, PatrolMap patrolMap) {
        return MapUploadResponse.builder()
                .mappingSessionId(session.getId())
                .mapId(patrolMap.getId())
                .mapUrl(patrolMap.getUrl())
                .mapVersion(patrolMap.getMapVersion())
                .mappingStatus(session.getStatus())
                .completedAt(session.getFinishedAt())
                .build();
    }
}
