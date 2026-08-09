package com.oneloop.event.event;

import com.oneloop.event.dto.response.EmergencyEventSseResponse;

public record EmergencyEventCreatedEvent(
        Long apartmentComplexId, EmergencyEventSseResponse response) {}
