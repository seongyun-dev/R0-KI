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

    public static MappingStatusEventResponse from(MappingSession session) {
        return of(session.getId(), session.getStatus());
    }

    public static MappingStatusEventResponse of(Long mappingSessionId, MappingStatus status) {
        return MappingStatusEventResponse.builder()
                .mappingSessionId(mappingSessionId)
                .status(status)
                .build();
    }
}
