package com.oneloop.event.dto.response;

import com.oneloop.event.domain.EventEvidence;
import com.oneloop.event.domain.MediaType;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "이벤트 증거자료 응답")
public class EventEvidenceResponse {
    @Schema(description = "미디어 유형", example = "IMAGE")
    private MediaType mediaType;

    @Schema(description = "파일 URL", example = "https://example.com/evidence/1.jpg")
    private String fileUrl;

    public static EventEvidenceResponse from(EventEvidence evidence) {
        return EventEvidenceResponse.builder()
                .mediaType(evidence.getMediaType())
                .fileUrl(evidence.getFileUrl())
                .build();
    }
}
