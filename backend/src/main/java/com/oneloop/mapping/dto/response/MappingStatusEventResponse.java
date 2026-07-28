package com.oneloop.mapping.dto.response;

import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "지도 생성 상태 SSE 이벤트")
@Getter
@Builder
public class MappingStatusEventResponse {

    @Schema(description = "지도 생성 세션 ID", example = "123")
    private Long mappingSessionId;

    @Schema(description = "지도 생성 상태", example = "MAPPING")
    private MappingStatus status;

    @Schema(description = "완료된 지도 ID. COMPLETED 상태에서만 전달", example = "15")
    private Long mapId;

    public static MappingStatusEventResponse from(MappingSession session) {
        return of(session.getId(), session.getStatus());
    }

    public static MappingStatusEventResponse from(MappingSession session, Long mapId) {
        return of(session.getId(), session.getStatus(), mapId);
    }

    public static MappingStatusEventResponse of(Long mappingSessionId, MappingStatus status) {
        return of(mappingSessionId, status, null);
    }

    public static MappingStatusEventResponse of(
            Long mappingSessionId, MappingStatus status, Long mapId) {
        return MappingStatusEventResponse.builder()
                .mappingSessionId(mappingSessionId)
                .status(status)
                .mapId(mapId)
                .build();
    }
}
