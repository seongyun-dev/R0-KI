package com.oneloop.robot.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.domain.RoutePosition;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.patrol.repository.RoutePositionRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.dto.response.RobotMapLocationResponse;
import com.oneloop.robot.repository.RobotRepository;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RobotLocationQueryService {

    private static final List<RobotStatus> PATROLLING_STATUSES =
            List.of(RobotStatus.PATROLLING, RobotStatus.OBSTACLE_STOP);

    private final RobotRepository robotRepository;
    private final PatrolRepository patrolRepository;
    private final RoutePositionRepository routePositionRepository;

    /**
     * 대시보드 최초 진입 시 표시할 순찰 중 로봇의 최신 위치와 현재 순찰 경로를 조회합니다.
     *
     * <p>이후 변경분은 SSE의 위치 이벤트와 상태·배터리 이벤트로 갱신합니다.
     */
    public List<RobotMapLocationResponse> findPatrollingLocations(Long apartmentComplexId) {
        return robotRepository
                .findAllByApartmentComplexIdAndStatusInOrderByIdAsc(
                        apartmentComplexId, PATROLLING_STATUSES)
                .stream()
                .map(this::toResponse)
                .toList();
    }

    /** 하단 목록에서 선택한 로봇은 순찰 여부와 관계없이 마지막으로 저장된 위치를 반환합니다. */
    public RobotMapLocationResponse findRobotLocation(Long apartmentComplexId, Long robotId) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexIdAndStatusNot(
                                robotId, apartmentComplexId, RobotStatus.DELETED)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        return toResponse(robot);
    }

    private RobotMapLocationResponse toResponse(PatrolRobot robot) {
        if (!PATROLLING_STATUSES.contains(robot.getStatus())) {
            return RobotMapLocationResponse.of(robot, List.of());
        }

        // 현재 진행 중인 순찰이 확인된 경우에만 그 순찰에 속한 경로 좌표를 함께 반환합니다.
        List<RoutePosition> routePositions =
                patrolRepository
                        .findFirstByRobotIdAndStatusOrderByStartedAtDesc(
                                robot.getId(), PatrolStatus.IN_PROGRESS)
                        .map(
                                patrol ->
                                        routePositionRepository.findAllByPatrolIdOrderByRecordedAt(
                                                patrol.getId()))
                        .orElseGet(List::of);
        return RobotMapLocationResponse.of(robot, routePositions);
    }
}
