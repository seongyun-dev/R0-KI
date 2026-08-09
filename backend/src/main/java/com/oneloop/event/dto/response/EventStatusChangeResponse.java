package com.oneloop.event.dto.response;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.ProcessingStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "이벤트 처리상태 변경 응답")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EventStatusChangeResponse {

    @Schema(description = "이벤트 ID", example = "501")
    private Long eventId;

    @Schema(description = "변경된 처리 상태", example = "PROCESSING")
    private ProcessingStatus processingStatus;

    @Schema(description = "변경 시각")
    private LocalDateTime updatedAt;

    public static EventStatusChangeResponse of(DetectedEvent event, LocalDateTime updatedAt) {
        return EventStatusChangeResponse.builder()
                .eventId(event.getId())
                .processingStatus(event.getProcessingStatus())
                .updatedAt(updatedAt)
                .build();
    }
}
