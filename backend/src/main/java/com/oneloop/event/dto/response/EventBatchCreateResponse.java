package com.oneloop.event.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "이벤트 일괄 생성 응답")
@Getter
@Builder
public class EventBatchCreateResponse {
    @Schema(description = "생성된 이벤트 목록 (요청 순서와 무관하게 tempId로 매칭)")
    private List<EventBatchCreatedItem> events;

    public static EventBatchCreateResponse of(List<EventBatchCreatedItem> events) {
        return EventBatchCreateResponse.builder().events(events).build();
    }
}
