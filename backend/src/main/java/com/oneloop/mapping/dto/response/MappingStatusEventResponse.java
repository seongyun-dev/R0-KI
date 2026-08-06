package com.oneloop.mapping.dto.response;

import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.domain.MappingStopCommandStatus;
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

    @Schema(description = "지도 생성 종료 명령 ID", nullable = true)
    private String stopCommandId;

    @Schema(description = "지도 생성 종료 명령 처리 상태", nullable = true)
    private MappingStopCommandStatus stopCommandStatus;

    @Schema(description = "지도 생성 종료 요청 실패 사유", nullable = true)
    private String reason;

    public static MappingStatusEventResponse from(MappingSession session) {
        return from(session, null);
    }

    public static MappingStatusEventResponse from(MappingSession session, Long mapId) {
        return MappingStatusEventResponse.builder()
                .mappingSessionId(session.getId())
                .status(session.getStatus())
                .mapId(mapId)
                .stopCommandId(session.getStopCommandId())
                .stopCommandStatus(session.getStopCommandStatus())
                .reason(session.getStopFailureReason())
                .build();
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

    public static MappingStatusEventResponse ofStopCommand(
            Long mappingSessionId,
            MappingStatus status,
            String stopCommandId,
            MappingStopCommandStatus stopCommandStatus,
            String reason) {
        return MappingStatusEventResponse.builder()
                .mappingSessionId(mappingSessionId)
                .status(status)
                .stopCommandId(stopCommandId)
                .stopCommandStatus(stopCommandStatus)
                .reason(reason)
                .build();
    }
}
