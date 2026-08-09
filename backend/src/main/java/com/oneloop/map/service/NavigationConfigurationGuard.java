package com.oneloop.map.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class NavigationConfigurationGuard {

    private static final List<PatrolStatus> LOCKING_STATUSES =
            List.of(PatrolStatus.IN_PROGRESS, PatrolStatus.STOP_REQUESTED);

    private final PatrolRepository patrolRepository;

    /** 호출자는 검사 대상 단지의 PatrolMap 행을 PESSIMISTIC_WRITE로 먼저 잠가야 한다. */
    public void assertMutable(Long apartmentComplexId) {
        if (patrolRepository.existsByRobotApartmentComplexIdAndStatusIn(
                apartmentComplexId, LOCKING_STATUSES)) {
            throw new BusinessException(ErrorCode.MAP_CONFIGURATION_LOCKED);
        }
    }
}
