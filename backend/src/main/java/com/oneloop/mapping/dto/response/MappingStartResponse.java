package com.oneloop.mapping.dto.response;

import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "지도 생성 시작 응답")
@Getter
@Builder
public class MappingStartResponse {

    private Long mappingSessionId;
    private Long robotId;
    private MappingStatus mappingStatus;
    private LocalDateTime createdAt;

    public static MappingStartResponse from(MappingSession session) {
        return MappingStartResponse.builder()
                .mappingSessionId(session.getId())
                .robotId(session.getRobot().getId())
                .mappingStatus(session.getStatus())
                .createdAt(session.getCreatedAt())
                .build();
    }
}
