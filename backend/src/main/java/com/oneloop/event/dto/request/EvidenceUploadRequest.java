package com.oneloop.event.dto.request;

import com.oneloop.event.domain.MediaType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import java.time.OffsetDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.web.multipart.MultipartFile;

@Schema(description = "증거자료 업로드 요청 (로봇 → 백엔드, multipart/form-data)")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EvidenceUploadRequest {

    @Schema(description = "증거 파일(사진/영상)")
    @NotNull(message = "file은 필수입니다.")
    private MultipartFile file;

    @Schema(description = "미디어 유형", example = "IMAGE")
    @NotNull(message = "mediaType은 필수입니다.")
    private MediaType mediaType;

    @Schema(description = "촬영 시각 - 없으면 업로드 시각으로 채움", example = "2026-07-23T14:15:30+09:00", nullable = true)
    private OffsetDateTime capturedAt;
}
