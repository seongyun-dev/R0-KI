package com.oneloop.map.util;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.patrol.domain.Patrol;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class EventCheckpointResolverTest {

    @Mock private CheckpointRepository checkpointRepository;
    @Mock private CheckpointLocator checkpointLocator;

    @InjectMocks private EventCheckpointResolver resolver;

    @Test
    void resolvesEachEventAgainstItsPatrolSnapshotMap() {
        DetectedEvent oldEvent = eventOnMap(11L);
        DetectedEvent newEvent = eventOnMap(22L);
        Checkpoint oldZone = mock(Checkpoint.class);
        Checkpoint newZone = mock(Checkpoint.class);
        BigDecimal oldX = BigDecimal.valueOf(11L);
        BigDecimal oldY = BigDecimal.ZERO;

        when(checkpointRepository.findAllByPatrolMapId(11L)).thenReturn(List.of(oldZone));
        when(checkpointRepository.findAllByPatrolMapId(22L)).thenReturn(List.of(newZone));
        when(oldEvent.getX()).thenReturn(oldX);
        when(oldEvent.getY()).thenReturn(oldY);
        when(checkpointLocator.resolveLocationName(List.of(oldZone), oldX, oldY))
                .thenReturn("old-zone");

        Map<Long, List<Checkpoint>> index =
                resolver.loadCheckpointIndex(List.of(oldEvent, newEvent));

        assertThat(resolver.resolveLocationName(oldEvent, index)).isEqualTo("old-zone");
        assertThat(resolver.checkpointsFor(oldEvent, index)).containsExactly(oldZone);
        assertThat(resolver.checkpointsFor(newEvent, index)).containsExactly(newZone);
        verify(checkpointRepository).findAllByPatrolMapId(11L);
        verify(checkpointRepository).findAllByPatrolMapId(22L);
    }

    @Test
    void doesNotProjectLegacyEventWithoutMapOntoCurrentMap() {
        DetectedEvent event = mock(DetectedEvent.class);

        Map<Long, List<Checkpoint>> index = resolver.loadCheckpointIndex(List.of(event));

        assertThat(index).isEmpty();
        assertThat(resolver.checkpointsFor(event, index)).isEmpty();
        verifyNoInteractions(checkpointRepository);
    }

    private DetectedEvent eventOnMap(Long mapId) {
        DetectedEvent event = mock(DetectedEvent.class);
        Patrol patrol = mock(Patrol.class);
        PatrolMap map = mock(PatrolMap.class);
        when(event.getPatrol()).thenReturn(patrol);
        when(patrol.getMap()).thenReturn(map);
        when(map.getId()).thenReturn(mapId);
        return event;
    }
}
