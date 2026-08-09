package com.oneloop.event.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "이벤트 생성 응답")
public class EventCreateResponse {
    @Schema(description = "생성된 이벤트 ID", example = "203")
    private Long eventId;

    public static EventCreateResponse of(Long eventId) {
        return EventCreateResponse.builder().eventId(eventId).build();
    }
}
