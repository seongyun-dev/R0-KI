package com.oneloop.map.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.NavigationWaypointAction;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.WaypointBatchReplaceRequest;
import com.oneloop.map.dto.request.WaypointReplaceItemRequest;
import com.oneloop.map.dto.response.WaypointSetResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.NavigationWaypointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NavigationWaypointService {

    private static final BigDecimal MIN_ACCEPTANCE_RADIUS = new BigDecimal("0.20");
    private static final BigDecimal MAX_ACCEPTANCE_RADIUS = new BigDecimal("1.00");
    private static final double MAP_BOUNDARY_EPSILON = 0.000_001D;

    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final NavigationWaypointRepository navigationWaypointRepository;
    private final NavigationConfigurationGuard navigationConfigurationGuard;

    public WaypointSetResponse findAll(Long apartmentComplexId, Long mapId) {
        PatrolMap patrolMap = findMap(apartmentComplexId, mapId);
        return WaypointSetResponse.from(patrolMap, findCurrent(patrolMap));
    }

    @Transactional
    public WaypointSetResponse replaceAll(
            Long apartmentComplexId, Long mapId, WaypointBatchReplaceRequest request) {
        PatrolMap patrolMap = findMapForUpdate(apartmentComplexId, mapId);
        validateRequestedMapVersion(patrolMap, request == null ? null : request.getMapVersion());

        List<WaypointReplaceItemRequest> ordered = validateRequest(patrolMap, request);
        Map<Long, Checkpoint> zones = resolveZones(patrolMap, ordered);
        List<NavigationWaypoint> replacements =
                ordered.stream()
                        .map(
                                item ->
                                        toEntity(
                                                patrolMap,
                                                item,
                                                item.getZoneId() == null
                                                        ? null
                                                        : zones.get(item.getZoneId())))
                        .toList();

        navigationConfigurationGuard.assertMutable(apartmentComplexId);
        navigationWaypointRepository.deleteAllByPatrolMapIdAndMapVersion(
                patrolMap.getId(), patrolMap.getMapVersion());
        List<NavigationWaypoint> saved = navigationWaypointRepository.saveAll(replacements);
        return WaypointSetResponse.from(patrolMap, saved);
    }

    public List<NavigationWaypoint> findCurrent(PatrolMap patrolMap) {
        if (patrolMap.getMapVersion() == null) {
            return List.of();
        }
        return navigationWaypointRepository.findAllByPatrolMapIdAndMapVersionOrderBySequenceAsc(
                patrolMap.getId(), patrolMap.getMapVersion());
    }

    public List<NavigationWaypoint> requireValidCurrentRoute(PatrolMap patrolMap) {
        List<NavigationWaypoint> waypoints = findCurrent(patrolMap);
        validateStoredRoute(patrolMap, waypoints);
        return waypoints;
    }

    public void validateMapMetadata(PatrolMap patrolMap) {
        if (!hasCompleteMapMetadata(patrolMap)) {
            throw new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
        }
    }

    private List<WaypointReplaceItemRequest> validateRequest(
            PatrolMap patrolMap, WaypointBatchReplaceRequest request) {
        if (request == null || request.getWaypoints() == null || request.getWaypoints().isEmpty()) {
            throw invalidRoute();
        }
        if (request.getWaypoints().stream()
                .anyMatch(waypoint -> waypoint == null || waypoint.getSequence() == null)) {
            throw invalidRoute();
        }
        validateMapMetadata(patrolMap);

        List<WaypointReplaceItemRequest> ordered =
                request.getWaypoints().stream()
                        .sorted(Comparator.comparing(WaypointReplaceItemRequest::getSequence))
                        .toList();
        validateRequestSequenceAndActions(ordered);
        validateRequestGeometry(patrolMap, ordered);
        return ordered;
    }

    private void validateRequestSequenceAndActions(List<WaypointReplaceItemRequest> ordered) {
        long destinationCount = 0;
        for (int index = 0; index < ordered.size(); index++) {
            WaypointReplaceItemRequest waypoint = ordered.get(index);
            if (waypoint == null
                    || waypoint.getSequence() == null
                    || waypoint.getSequence() != index + 1
                    || waypoint.getX() == null
                    || waypoint.getY() == null
                    || waypoint.getAction() == null) {
                throw invalidRoute();
            }
            if (waypoint.getAction() == NavigationWaypointAction.DESTINATION) {
                destinationCount++;
            }
            normalizeStoragePrecision(waypoint);
            validateAcceptanceRadius(waypoint.getAcceptanceRadius());
            validateFinite(waypoint.getX());
            validateFinite(waypoint.getY());
            if (waypoint.getYaw() != null) {
                validateFinite(waypoint.getYaw());
            }
        }

        if (destinationCount != 1
                || ordered.get(ordered.size() - 1).getAction()
                        != NavigationWaypointAction.DESTINATION) {
            throw invalidRoute();
        }
    }

    private void validateRequestGeometry(
            PatrolMap patrolMap, List<WaypointReplaceItemRequest> ordered) {
        for (WaypointReplaceItemRequest waypoint : ordered) {
            if (!isInsideMap(patrolMap, waypoint.getX(), waypoint.getY())) {
                throw invalidRoute();
            }
        }
        for (int index = 1; index < ordered.size(); index++) {
            WaypointReplaceItemRequest previous = ordered.get(index - 1);
            WaypointReplaceItemRequest current = ordered.get(index);
            validateConsecutiveDistance(
                    previous.getX(),
                    previous.getY(),
                    effectiveRadius(previous.getAcceptanceRadius()),
                    current.getX(),
                    current.getY(),
                    effectiveRadius(current.getAcceptanceRadius()),
                    ErrorCode.INVALID_WAYPOINT_ROUTE);
        }
    }

    private Map<Long, Checkpoint> resolveZones(
            PatrolMap patrolMap, List<WaypointReplaceItemRequest> ordered) {
        Set<Long> requestedZoneIds =
                ordered.stream()
                        .map(WaypointReplaceItemRequest::getZoneId)
                        .filter(java.util.Objects::nonNull)
                        .collect(Collectors.toCollection(HashSet::new));
        if (requestedZoneIds.isEmpty()) {
            return Map.of();
        }

        List<Checkpoint> zones =
                checkpointRepository.findAllActiveByPatrolMapIdAndIdIn(
                        patrolMap.getId(), List.copyOf(requestedZoneIds));
        if (zones.size() != requestedZoneIds.size()) {
            throw invalidRoute();
        }
        return zones.stream().collect(Collectors.toMap(Checkpoint::getId, Function.identity()));
    }

    private NavigationWaypoint toEntity(
            PatrolMap patrolMap, WaypointReplaceItemRequest request, Checkpoint zone) {
        return new NavigationWaypoint(
                patrolMap,
                patrolMap.getMapVersion(),
                request.getSequence(),
                request.getX(),
                request.getY(),
                request.getAction(),
                request.getYaw(),
                request.getAcceptanceRadius(),
                zone);
    }

    private void validateStoredRoute(PatrolMap patrolMap, List<NavigationWaypoint> waypoints) {
        validateMapMetadata(patrolMap);
        if (waypoints.isEmpty()) {
            throw new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
        }

        long destinationCount = 0;
        Set<Integer> sequences = new HashSet<>();
        for (int index = 0; index < waypoints.size(); index++) {
            NavigationWaypoint waypoint = waypoints.get(index);
            if (waypoint.getSequence() == null
                    || waypoint.getSequence() != index + 1
                    || !sequences.add(waypoint.getSequence())
                    || waypoint.getAction() == null
                    || waypoint.getX() == null
                    || waypoint.getY() == null
                    || waypoint.getAcceptanceRadius() == null
                    || !isInsideMap(patrolMap, waypoint.getX(), waypoint.getY())) {
                throw new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
            }
            if (waypoint.getAction() == NavigationWaypointAction.DESTINATION) {
                destinationCount++;
            }
            if (waypoint.getZone() != null
                    && (!waypoint.getZone().isActive()
                            || !waypoint.getZone()
                                    .getPatrolMap()
                                    .getId()
                                    .equals(patrolMap.getId()))) {
                throw new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
            }
            validateStoredAcceptanceRadius(waypoint.getAcceptanceRadius());
        }
        if (destinationCount != 1
                || waypoints.get(waypoints.size() - 1).getAction()
                        != NavigationWaypointAction.DESTINATION) {
            throw new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
        }
        for (int index = 1; index < waypoints.size(); index++) {
            NavigationWaypoint previous = waypoints.get(index - 1);
            NavigationWaypoint current = waypoints.get(index);
            validateConsecutiveDistance(
                    previous.getX(),
                    previous.getY(),
                    previous.getAcceptanceRadius(),
                    current.getX(),
                    current.getY(),
                    current.getAcceptanceRadius(),
                    ErrorCode.NAVIGATION_CONFIG_NOT_READY);
        }
    }

    private void validateConsecutiveDistance(
            BigDecimal firstX,
            BigDecimal firstY,
            BigDecimal firstRadius,
            BigDecimal secondX,
            BigDecimal secondY,
            BigDecimal secondRadius,
            ErrorCode errorCode) {
        double distance =
                Math.hypot(
                        secondX.subtract(firstX).doubleValue(),
                        secondY.subtract(firstY).doubleValue());
        double minimumDistance = firstRadius.add(secondRadius).doubleValue();
        if (!Double.isFinite(distance) || distance <= minimumDistance) {
            throw new BusinessException(errorCode);
        }
    }

    private boolean isInsideMap(PatrolMap patrolMap, BigDecimal x, BigDecimal y) {
        if (!hasCompleteMapMetadata(patrolMap)) {
            return false;
        }

        double originX = patrolMap.getOriginX().doubleValue();
        double originY = patrolMap.getOriginY().doubleValue();
        double originYaw = patrolMap.getOriginYaw().doubleValue();
        double dx = x.doubleValue() - originX;
        double dy = y.doubleValue() - originY;
        double cos = Math.cos(originYaw);
        double sin = Math.sin(originYaw);
        double localX = cos * dx + sin * dy;
        double localY = -sin * dx + cos * dy;
        double mapWidth = patrolMap.getWidth() * patrolMap.getResolution().doubleValue();
        double mapHeight = patrolMap.getHeight() * patrolMap.getResolution().doubleValue();

        return Double.isFinite(localX)
                && Double.isFinite(localY)
                && localX >= -MAP_BOUNDARY_EPSILON
                && localY >= -MAP_BOUNDARY_EPSILON
                && localX < mapWidth
                && localY < mapHeight;
    }

    private boolean hasCompleteMapMetadata(PatrolMap patrolMap) {
        if (patrolMap == null
                || patrolMap.getId() == null
                || patrolMap.getMapVersion() == null
                || patrolMap.getResolution() == null
                || patrolMap.getOriginX() == null
                || patrolMap.getOriginY() == null
                || patrolMap.getOriginYaw() == null
                || patrolMap.getWidth() == null
                || patrolMap.getHeight() == null) {
            return false;
        }
        double resolution = patrolMap.getResolution().doubleValue();
        double originX = patrolMap.getOriginX().doubleValue();
        double originY = patrolMap.getOriginY().doubleValue();
        double yaw = patrolMap.getOriginYaw().doubleValue();
        return Double.isFinite(resolution)
                && resolution > 0
                && Double.isFinite(originX)
                && Double.isFinite(originY)
                && Double.isFinite(yaw)
                && patrolMap.getWidth() > 0
                && patrolMap.getHeight() > 0;
    }

    private void validateRequestedMapVersion(PatrolMap patrolMap, Integer requestedMapVersion) {
        if (requestedMapVersion == null
                || patrolMap.getMapVersion() == null
                || !patrolMap.getMapVersion().equals(requestedMapVersion)) {
            throw new BusinessException(ErrorCode.MAP_VERSION_CONFLICT);
        }
    }

    private void validateAcceptanceRadius(BigDecimal radius) {
        if (radius == null) {
            return;
        }
        validateFinite(radius);
        if (radius.compareTo(MIN_ACCEPTANCE_RADIUS) < 0
                || radius.compareTo(MAX_ACCEPTANCE_RADIUS) > 0) {
            throw invalidRoute();
        }
    }

    private void validateStoredAcceptanceRadius(BigDecimal radius) {
        if (!Double.isFinite(radius.doubleValue())
                || radius.compareTo(MIN_ACCEPTANCE_RADIUS) < 0
                || radius.compareTo(MAX_ACCEPTANCE_RADIUS) > 0) {
            throw new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY);
        }
    }

    private BigDecimal effectiveRadius(BigDecimal radius) {
        return radius == null ? NavigationWaypoint.DEFAULT_ACCEPTANCE_RADIUS : radius;
    }

    private void normalizeStoragePrecision(WaypointReplaceItemRequest waypoint) {
        waypoint.setX(normalize(waypoint.getX(), 7, 3));
        waypoint.setY(normalize(waypoint.getY(), 7, 3));
        if (waypoint.getYaw() != null) {
            waypoint.setYaw(normalize(waypoint.getYaw(), 3, 4));
        }
        if (waypoint.getAcceptanceRadius() != null) {
            waypoint.setAcceptanceRadius(normalize(waypoint.getAcceptanceRadius(), 2, 3));
        }
    }

    private BigDecimal normalize(BigDecimal value, int maxIntegerDigits, int scale) {
        try {
            BigDecimal normalized = value.setScale(scale, RoundingMode.UNNECESSARY);
            int integerDigits = Math.max(0, normalized.precision() - normalized.scale());
            if (integerDigits > maxIntegerDigits) {
                throw invalidRoute();
            }
            return normalized;
        } catch (ArithmeticException precisionLoss) {
            throw invalidRoute();
        }
    }

    private void validateFinite(BigDecimal value) {
        if (!Double.isFinite(value.doubleValue())) {
            throw invalidRoute();
        }
    }

    private PatrolMap findMap(Long apartmentComplexId, Long mapId) {
        return patrolMapRepository
                .findByIdAndApartmentComplexId(mapId, apartmentComplexId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
    }

    private PatrolMap findMapForUpdate(Long apartmentComplexId, Long mapId) {
        return patrolMapRepository
                .findForUpdateByIdAndApartmentComplexId(mapId, apartmentComplexId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
    }

    private BusinessException invalidRoute() {
        return new BusinessException(ErrorCode.INVALID_WAYPOINT_ROUTE);
    }
}
