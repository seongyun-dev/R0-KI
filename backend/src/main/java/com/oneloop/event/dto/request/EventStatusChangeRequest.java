package com.oneloop.event.dto.request;

import com.oneloop.event.domain.ProcessingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "이벤트 처리상태 변경 요청")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EventStatusChangeRequest {

    @Schema(description = "변경할 처리 상태", example = "PROCESSING", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "processingStatus는 필수입니다.")
    private ProcessingStatus processingStatus;

    @Schema(description = "처리 메모", example = "차주 연락 후 이동 조치", nullable = true)
    @Size(max = 500, message = "메모는 500자 이하여야 합니다.")
    private String processingNote;
}
