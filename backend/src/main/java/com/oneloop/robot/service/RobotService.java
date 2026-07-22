package com.oneloop.robot.service;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.response.PageResponse;
import com.oneloop.map.domain.Checkpoint;
import com.oneloop.map.domain.CheckpointType;
import com.oneloop.map.repository.CheckpointRepository;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.dto.response.PatrolSummaryResponse;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.dto.request.RobotRegisterRequest;
import com.oneloop.robot.dto.response.RobotDetailResponse;
import com.oneloop.robot.dto.response.RobotListResponse;
import com.oneloop.robot.dto.response.RobotRegisterResponse;
import com.oneloop.robot.dto.response.RobotStatsResponse;
import com.oneloop.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class RobotService {

    private final RobotRepository robotRepository;
    private final ApartmentComplexRepository apartmentComplexRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final CheckpointRepository checkpointRepository;
    private final PatrolRepository patrolRepository;

    /**
     * 로그인한 관리자의 소속 단지에 새로운 순찰로봇을 등록한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param request 로봇 이름과 시리얼 번호
     * @return 등록된 로봇 정보
     * @throws BusinessException 시리얼 번호가 이미 등록되어 있는 경우
     */
    @Transactional
    public RobotRegisterResponse register(Long apartmentComplexId, RobotRegisterRequest request) {
        // 시리얼 번호 중복 시 등록 거부
        if (robotRepository.findBySerialNumber(request.getSerialNumber()).isPresent()) {
            throw new BusinessException(ErrorCode.ROBOT_SERIAL_NUMBER_DUPLICATE);
        }

        ApartmentComplex apartmentComplex = apartmentComplexRepository.getReferenceById(apartmentComplexId);
        PatrolRobot robot =
                new PatrolRobot(apartmentComplex, request.getName(), request.getSerialNumber());
        return RobotRegisterResponse.from(robotRepository.save(robot));
    }

    /**
     * 로그인한 관리자의 소속 단지에 등록된 순찰로봇 목록을 조회한다. 각 로봇의 현재 좌표가 속한 체크포인트 유형을 함께 반환한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param pageable 페이지 정보
     * @return 순찰로봇 페이지 목록
     */
    public PageResponse<RobotListResponse> findAll(Long apartmentComplexId, Pageable pageable) {
        // 로그인한 관리자의 단지에 속한 로봇만 페이지 조회
        Page<PatrolRobot> robots =
                robotRepository.findAllByApartmentComplexId(apartmentComplexId, pageable);

        // 단지의 맵과 체크포인트를 한 번만 조회해 모든 로봇에 재사용
        List<Checkpoint> checkpoints =
                patrolMapRepository
                        .findByApartmentComplexId(apartmentComplexId)
                        .map(map -> checkpointRepository.findAllByPatrolMapId(map.getId()))
                        .orElseGet(List::of);

        Page<RobotListResponse> responses =
                robots.map(
                        robot ->
                                RobotListResponse.of(robot, matchCheckpointType(robot, checkpoints)));
        return PageResponse.from(responses);
    }

    /**
     * 로그인한 관리자의 소속 단지 순찰로봇 현황(전체/순찰중/대기·충전중 수)을 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @return 로봇 현황 통계
     */
    public RobotStatsResponse getStats(Long apartmentComplexId) {
        long totalCount = robotRepository.countByApartmentComplexId(apartmentComplexId);
        long patrollingCount =
                robotRepository.countByApartmentComplexIdAndStatusIn(
                        apartmentComplexId, List.of(RobotStatus.PATROLLING));
        long idleOrChargingCount =
                robotRepository.countByApartmentComplexIdAndStatusIn(
                        apartmentComplexId, List.of(RobotStatus.IDLE, RobotStatus.CHARGING));

        return new RobotStatsResponse(totalCount, patrollingCount, idleOrChargingCount);
    }

    /**
     * 로그인한 관리자의 소속 단지에 등록된 순찰로봇 하나를 상세 조회한다.
     *
     * @param apartmentComplexId 로그인한 관리자의 소속 단지 식별자
     * @param robotId 조회할 로봇 식별자
     * @return 로봇 상세 정보
     * @throws BusinessException 해당 단지에 그 로봇이 없는 경우
     */
    public RobotDetailResponse findById(Long apartmentComplexId, Long robotId) {
        PatrolRobot robot =
                robotRepository
                        .findByIdAndApartmentComplexId(robotId, apartmentComplexId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.ROBOT_NOT_FOUND));

        // 최근 순찰 기록 미리보기 5건 (조정 가능)
        List<PatrolSummaryResponse> recentPatrols =
                patrolRepository
                        .findAllByRobotIdOrderByStartedAtDesc(robotId, PageRequest.of(0, 5))
                        .map(PatrolSummaryResponse::from)
                        .getContent();

        return RobotDetailResponse.from(robot, calculateWeeklyOperationRate(robotId), recentPatrols);
    }

    // 이번 주(월요일 0시)가 시작된 이후 지금까지 경과한 시간 대비, 그동안 순찰한 시간의 비율(%)을 계산한다.
    private double calculateWeeklyOperationRate(Long robotId) {
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime weekStart =
                now.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)).toLocalDate().atStartOfDay();

        long elapsedSeconds = Duration.between(weekStart, now).getSeconds();
        if (elapsedSeconds <= 0) {
            return 0.0;
        }

        long activeSeconds =
                patrolRepository.findAllByRobotIdAndStartedAtGreaterThanEqual(robotId, weekStart).stream()
                        .mapToLong(patrol -> patrolActiveSeconds(patrol, now))
                        .sum();

        return Math.min(100.0, Math.round((activeSeconds * 1000.0 / elapsedSeconds)) / 10.0);
    }

    // 완료된 순찰은 저장된 총 소요시간을, 진행중인 순찰은 시작 시각부터 지금까지의 경과시간을 사용한다.
    private long patrolActiveSeconds(Patrol patrol, LocalDateTime now) {
        if (patrol.getTotalDuration() != null) {
            return patrol.getTotalDuration();
        }
        return Duration.between(patrol.getStartedAt(), now).getSeconds();
    }

    // 로봇 좌표가 속한 체크포인트의 유형을 찾는다. 좌표가 없거나 어느 구역에도 속하지 않으면 null.
    private CheckpointType matchCheckpointType(PatrolRobot robot, List<Checkpoint> checkpoints) {
        BigDecimal x = robot.getXCoordinate();
        BigDecimal y = robot.getYCoordinate();
        if (x == null || y == null) {
            return null;
        }

        return checkpoints.stream()
                .filter(checkpoint -> contains(checkpoint, x, y))
                .findFirst()
                .map(Checkpoint::getType)
                .orElse(null);
    }

    // 좌표(x, y)가 체크포인트의 사각 영역(minX~maxX, minY~maxY) 안에 있는지 판별한다.
    private boolean contains(Checkpoint checkpoint, BigDecimal x, BigDecimal y) {
        return x.compareTo(checkpoint.getMinX()) >= 0
                && x.compareTo(checkpoint.getMaxX()) <= 0
                && y.compareTo(checkpoint.getMinY()) >= 0
                && y.compareTo(checkpoint.getMaxY()) <= 0;
    }
}
