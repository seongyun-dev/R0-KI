package com.oneloop.event.event;

import com.oneloop.event.dto.response.GeneralEventsCreatedSseResponse;

public record GeneralEventsCreatedEvent(
        Long apartmentComplexId, GeneralEventsCreatedSseResponse response) {}
