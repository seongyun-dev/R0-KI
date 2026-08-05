package com.oneloop.map.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.request.ZoneBatchCreateRequest;
import com.oneloop.map.dto.request.ZoneCreateRequest;
import com.oneloop.map.dto.response.ZoneResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import java.math.BigDecimal;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ZoneService {

    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;

    @Transactional
    public List<ZoneResponse> createAll(
            Long apartmentComplexId, Long mapId, ZoneBatchCreateRequest request) {
        PatrolMap patrolMap = findMap(apartmentComplexId, mapId);
        return saveAll(patrolMap, request);
    }

    @Transactional
    public List<ZoneResponse> replaceAll(
            Long apartmentComplexId, Long mapId, ZoneBatchCreateRequest request) {
        PatrolMap patrolMap = findMap(apartmentComplexId, mapId);
        checkpointRepository.deleteAllByPatrolMapId(mapId);
        checkpointRepository.flush();
        return saveAll(patrolMap, request);
    }

    private List<ZoneResponse> saveAll(
            PatrolMap patrolMap, ZoneBatchCreateRequest request) {
        List<Checkpoint> checkpoints =
                request.getZones().stream()
                        .map(zone -> toCheckpoint(patrolMap, zone))
                        .toList();

        return checkpointRepository.saveAll(checkpoints).stream()
                .map(ZoneResponse::from)
                .toList();
    }

    public List<ZoneResponse> findAll(Long apartmentComplexId, Long mapId) {
        findMap(apartmentComplexId, mapId);
        return checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(mapId).stream()
                .map(ZoneResponse::from)
                .toList();
    }

    private PatrolMap findMap(Long apartmentComplexId, Long mapId) {
        return patrolMapRepository
                .findByIdAndApartmentComplexId(mapId, apartmentComplexId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MAP_NOT_FOUND));
    }

    private Checkpoint toCheckpoint(PatrolMap patrolMap, ZoneCreateRequest request) {
        BigDecimal minX = request.getStartX().min(request.getEndX());
        BigDecimal minY = request.getStartY().min(request.getEndY());
        BigDecimal maxX = request.getStartX().max(request.getEndX());
        BigDecimal maxY = request.getStartY().max(request.getEndY());
        validateBounds(minX, minY, maxX, maxY);

        return new Checkpoint(
                patrolMap,
                request.getType(),
                request.getName().trim(),
                minX,
                minY,
                maxX,
                maxY);
    }

    private void validateBounds(
            BigDecimal minX, BigDecimal minY, BigDecimal maxX, BigDecimal maxY) {
        if (minX.compareTo(maxX) == 0 || minY.compareTo(maxY) == 0) {
            throw new BusinessException(ErrorCode.INVALID_ZONE_BOUNDS);
        }
    }
}
