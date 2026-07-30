package com.oneloop.event.dto.response;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class GeneralEventsCreatedSseResponse {

    private Long patrolId;
    private int createdCount;

    public static GeneralEventsCreatedSseResponse of(Long patrolId, int createdCount) {
        return GeneralEventsCreatedSseResponse.builder()
                .patrolId(patrolId)
                .createdCount(createdCount)
                .build();
    }
}
