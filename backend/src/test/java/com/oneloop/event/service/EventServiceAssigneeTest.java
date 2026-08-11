package com.oneloop.event.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventProcessingHistory;
import com.oneloop.event.dto.request.EventPeriodFilter;
import com.oneloop.event.dto.response.EventListResponse;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.event.repository.EventEvidenceRepository;
import com.oneloop.event.repository.EventProcessingHistoryRepository;
import com.oneloop.global.response.PageResponse;
import com.oneloop.map.util.EventCheckpointResolver;
import com.oneloop.member.repository.MemberRepository;
import com.oneloop.robot.domain.PatrolRobot;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

@ExtendWith(MockitoExtension.class)
class EventServiceAssigneeTest {

    @Mock private DetectedEventRepository detectedEventRepository;
    @Mock private EventProcessingHistoryRepository eventProcessingHistoryRepository;
    @Mock private EventEvidenceRepository eventEvidenceRepository;
    @Mock private EventCheckpointResolver eventCheckpointResolver;
    @Mock private MemberRepository memberRepository;
    @Mock private EmergencyPatrolResumeService emergencyPatrolResumeService;

    @InjectMocks private EventService eventService;

    @Test
    void listsAutomaticallyCompletedEventWithoutAssignee() {
        long apartmentComplexId = 2L;
        DetectedEvent event = mock(DetectedEvent.class);
        PatrolRobot robot = mock(PatrolRobot.class);
        EventProcessingHistory history = mock(EventProcessingHistory.class);
        Pageable pageable = PageRequest.of(0, 10);

        when(event.getId()).thenReturn(1851L);
        when(event.getRobot()).thenReturn(robot);
        when(robot.getName()).thenReturn("R0-Ki");
        when(history.getEvent()).thenReturn(event);
        when(history.getProcessingMember()).thenReturn(null);
        when(detectedEventRepository.findAllByFilter(
                        eq(apartmentComplexId),
                        isNull(),
                        isNull(),
                        isNull(),
                        isNull(),
                        eq(pageable)))
                .thenReturn(new PageImpl<>(List.of(event), pageable, 1));
        when(eventProcessingHistoryRepository.findAllByEventIdInOrderByChangedAtDesc(
                        List.of(event.getId())))
                .thenReturn(List.of(history));

        PageResponse<EventListResponse> response =
                eventService.findAll(
                        apartmentComplexId, null, null, EventPeriodFilter.ALL, pageable);

        assertThat(response.content()).hasSize(1);
        assertThat(response.content().getFirst().getAssignee()).isNull();
    }
}
