package com.oneloop.map.util;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.repository.CheckpointRepository;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/** Resolves an event location against the map captured by its patrol. */
@Component
@RequiredArgsConstructor
public class EventCheckpointResolver {

    private final CheckpointRepository checkpointRepository;
    private final CheckpointLocator checkpointLocator;

    public Map<Long, List<Checkpoint>> loadCheckpointIndex(
            Collection<DetectedEvent> events) {
        Map<Long, List<Checkpoint>> checkpointsByMap = new LinkedHashMap<>();
        events.stream()
                .map(this::resolveMapId)
                .filter(Objects::nonNull)
                .distinct()
                .forEach(
                        mapId ->
                                checkpointsByMap.put(
                                        mapId,
                                        checkpointRepository.findAllByPatrolMapId(mapId)));
        return checkpointsByMap;
    }

    public List<Checkpoint> checkpointsFor(
            DetectedEvent event, Map<Long, List<Checkpoint>> checkpointsByMap) {
        Long mapId = resolveMapId(event);
        return mapId == null ? List.of() : checkpointsByMap.getOrDefault(mapId, List.of());
    }

    public Optional<Checkpoint> findContaining(
            DetectedEvent event, Map<Long, List<Checkpoint>> checkpointsByMap) {
        return checkpointLocator.findContaining(
                checkpointsFor(event, checkpointsByMap), event.getX(), event.getY());
    }

    public String resolveLocationName(
            DetectedEvent event, Map<Long, List<Checkpoint>> checkpointsByMap) {
        return checkpointLocator.resolveLocationName(
                checkpointsFor(event, checkpointsByMap), event.getX(), event.getY());
    }

    private Long resolveMapId(DetectedEvent event) {
        if (event == null || event.getPatrol() == null || event.getPatrol().getMap() == null) {
            return null;
        }
        return event.getPatrol().getMap().getId();
    }
}
