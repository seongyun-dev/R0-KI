package com.oneloop.mapping.dto.response;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class MappingStopResponse {
    private Long mappingSessionId;
    private String commandId;
}
