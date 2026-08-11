package com.oneloop.event.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.EventProcessingHistory;
import com.oneloop.event.domain.ProcessingStatus;
import com.oneloop.event.dto.request.EventStatusChangeRequest;
import com.oneloop.event.repository.DetectedEventRepository;
import com.oneloop.event.repository.EventEvidenceRepository;
import com.oneloop.event.repository.EventProcessingHistoryRepository;
import com.oneloop.map.util.EventCheckpointResolver;
import com.oneloop.member.domain.Member;
import com.oneloop.member.repository.MemberRepository;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class EventServiceEmergencyResumeTest {

    @Mock private DetectedEventRepository detectedEventRepository;
    @Mock private EventProcessingHistoryRepository eventProcessingHistoryRepository;
    @Mock private EventEvidenceRepository eventEvidenceRepository;
    @Mock private EventCheckpointResolver eventCheckpointResolver;
    @Mock private MemberRepository memberRepository;
    @Mock private EmergencyPatrolResumeService emergencyPatrolResumeService;
    @Mock private DetectedEvent event;
    @Mock private Member member;

    @InjectMocks private EventService eventService;

    @Test
    void completingEventRequestsEligibleEmergencyResume() {
        stubStatusChange(ProcessingStatus.COMPLETED);

        eventService.changeStatus(
                2L,
                3L,
                501L,
                EventStatusChangeRequest.builder()
                        .processingStatus(ProcessingStatus.COMPLETED)
                        .processingNote("현장 조치 완료")
                        .build());

        verify(event).changeStatus(ProcessingStatus.COMPLETED);
        verify(emergencyPatrolResumeService).resumeIfEligible(event);
    }

    @Test
    void processingStateDoesNotRequestRobotResume() {
        stubStatusChange(ProcessingStatus.PROCESSING);

        eventService.changeStatus(
                2L,
                3L,
                501L,
                EventStatusChangeRequest.builder()
                        .processingStatus(ProcessingStatus.PROCESSING)
                        .build());

        verify(event).changeStatus(ProcessingStatus.PROCESSING);
        verify(emergencyPatrolResumeService, never()).resumeIfEligible(any());
    }

    private void stubStatusChange(ProcessingStatus status) {
        when(detectedEventRepository.findByIdAndRobotApartmentComplexId(501L, 2L))
                .thenReturn(Optional.of(event));
        when(memberRepository.getReferenceById(3L)).thenReturn(member);
        when(eventProcessingHistoryRepository.save(any(EventProcessingHistory.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        when(event.getProcessingStatus()).thenReturn(status);
    }
}
