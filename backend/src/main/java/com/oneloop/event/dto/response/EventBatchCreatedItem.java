package com.oneloop.event.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Getter;

@Schema(description = "일괄 생성된 이벤트 1건 (요청의 tempId와 매칭)")
@Getter
@Builder
public class EventBatchCreatedItem {
    @Schema(description = "요청 시 로봇이 붙인 임시 식별자", example = "e1")
    private String tempId;

    @Schema(description = "생성된 이벤트 ID", example = "150")
    private Long eventId;

    public static EventBatchCreatedItem of(String tempId, Long eventId) {
        return EventBatchCreatedItem.builder().tempId(tempId).eventId(eventId).build();
    }
}
