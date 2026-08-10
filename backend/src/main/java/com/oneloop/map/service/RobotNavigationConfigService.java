package com.oneloop.map.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.map.domain.NavigationWaypoint;
import com.oneloop.map.domain.PatrolMap;
import com.oneloop.map.dto.response.NavigationConfigResponse;
import com.oneloop.map.dto.response.ZoneResponse;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RobotNavigationConfigService {

    private final RobotRepository robotRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final NavigationWaypointService navigationWaypointService;

    public NavigationConfigResponse get(Long robotId) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndStatusNot(robotId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));
        PatrolMap patrolMap =
                patrolMapRepository
                        .findByApartmentComplexId(robot.getApartmentComplex().getId())
                        .orElseThrow(
                                () -> new BusinessException(ErrorCode.NAVIGATION_CONFIG_NOT_READY));
        List<NavigationWaypoint> waypoints =
                navigationWaypointService.requireValidCurrentRoute(patrolMap);
        List<ZoneResponse> zones =
                checkpointRepository.findAllByPatrolMapIdOrderByIdAsc(patrolMap.getId()).stream()
                        .map(ZoneResponse::from)
                        .toList();
        return NavigationConfigResponse.of(patrolMap, zones, waypoints);
    }
}
