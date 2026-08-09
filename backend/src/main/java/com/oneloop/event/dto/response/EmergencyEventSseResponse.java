package com.oneloop.event.dto.response;

import com.oneloop.event.domain.EventType;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.domain.RiskLevel;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class EmergencyEventSseResponse {

    private Long eventId;
    private EventType eventType;
    private String title;
    private LocalDateTime occurredAt;
    private String location;
    private String robotName;
    private RiskLevel riskLevel;
    private ProcessingStatus processingStatus;
    private Long mapId;
    private BigDecimal x;
    private BigDecimal y;
}
