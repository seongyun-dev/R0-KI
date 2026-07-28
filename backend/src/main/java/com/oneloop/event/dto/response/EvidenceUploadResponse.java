package com.oneloop.event.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "증거자료 업로드 응답")
@Getter
@Builder
public class EvidenceUploadResponse {
    @Schema(description = "생성된 증거자료 ID", example = "301")
    private Long evidenceId;

    public static EvidenceUploadResponse of(Long evidenceId) {
        return EvidenceUploadResponse.builder().evidenceId(evidenceId).build();
    }
}
