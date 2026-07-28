package com.oneloop.event.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "이벤트 일괄 생성 요청 (로봇 → 백엔드, 쓰레기탐지·분리수거장포화 전용)")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EventBatchCreateRequest {

    @Schema(description = "생성할 이벤트 목록")
    @NotEmpty(message = "events는 최소 1건 이상이어야 합니다.")
    @Valid
    private List<EventBatchItemRequest> events;
}
