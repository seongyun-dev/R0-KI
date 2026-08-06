package com.oneloop.mapping.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import com.oneloop.mapping.domain.MappingStopCommandStatus;
import com.oneloop.mapping.dto.response.MappingStatusEventResponse;
import com.oneloop.mapping.event.MappingStatusChangedEventListener;
import com.oneloop.mapping.event.MappingStopCommandStatusChangedEvent;
import com.oneloop.robot.domain.PatrolRobot;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class MappingStatusChangedEventListenerTest {

    @Mock private MappingSseService mappingSseService;
    @Mock private ApartmentComplex apartmentComplex;

    @Test
    void stopCommandResultUsesExistingMappingStatusChannel() {
        MappingStatusChangedEventListener listener =
                new MappingStatusChangedEventListener(mappingSseService);

        listener.handleStopCommand(
                new MappingStopCommandStatusChangedEvent(
                        123L,
                        MappingStatus.MAPPING,
                        "stop-command",
                        MappingStopCommandStatus.FAILED,
                        "MAPPING_NOT_ACTIVE"));

        ArgumentCaptor<MappingStatusEventResponse> responseCaptor =
                ArgumentCaptor.forClass(MappingStatusEventResponse.class);
        verify(mappingSseService).broadcast(eq(123L), responseCaptor.capture());
        MappingStatusEventResponse response = responseCaptor.getValue();
        assertThat(response.getMappingSessionId()).isEqualTo(123L);
        assertThat(response.getStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(response.getStopCommandId()).isEqualTo("stop-command");
        assertThat(response.getStopCommandStatus()).isEqualTo(MappingStopCommandStatus.FAILED);
        assertThat(response.getReason()).isEqualTo("MAPPING_NOT_ACTIVE");
    }

    @Test
    void initialSnapshotContainsPersistedStopCommandResult() {
        MappingSession session = mappingSession();
        session.startMapping();
        session.prepareStop("stop-command");
        session.failStop("MAPPING_NOT_ACTIVE");

        MappingStatusEventResponse response = MappingStatusEventResponse.from(session, null);

        assertThat(response.getMappingSessionId()).isEqualTo(123L);
        assertThat(response.getStatus()).isEqualTo(MappingStatus.MAPPING);
        assertThat(response.getStopCommandId()).isEqualTo("stop-command");
        assertThat(response.getStopCommandStatus()).isEqualTo(MappingStopCommandStatus.FAILED);
        assertThat(response.getReason()).isEqualTo("MAPPING_NOT_ACTIVE");
    }

    @Test
    void legacyPayloadConsumerCanIgnoreNewOptionalFields() throws Exception {
        ObjectMapper objectMapper =
                new ObjectMapper()
                        .findAndRegisterModules()
                        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        MappingSession session = mappingSession();
        session.startMapping();
        session.prepareStop("stop-command");
        session.acknowledgeStop();

        String payload =
                objectMapper.writeValueAsString(MappingStatusEventResponse.from(session, null));
        LegacyMappingStatusPayload legacy =
                objectMapper.readValue(payload, LegacyMappingStatusPayload.class);

        assertThat(legacy.mappingSessionId()).isEqualTo(123L);
        assertThat(legacy.status()).isEqualTo(MappingStatus.MAPPING);
        assertThat(legacy.mapId()).isNull();
    }

    private MappingSession mappingSession() {
        PatrolRobot robot = new PatrolRobot(apartmentComplex, "mapping-robot", "robot-key");
        MappingSession session = new MappingSession(apartmentComplex, robot, "start-command");
        ReflectionTestUtils.setField(session, "id", 123L);
        return session;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record LegacyMappingStatusPayload(
            Long mappingSessionId, MappingStatus status, Long mapId) {}
}
