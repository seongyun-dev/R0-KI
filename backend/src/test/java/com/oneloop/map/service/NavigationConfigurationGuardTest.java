package com.oneloop.map.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class NavigationConfigurationGuardTest {

    @Mock private PatrolRepository patrolRepository;

    @Test
    void permitsConfigurationChangeWhenNoPatrolIsActive() {
        when(patrolRepository.existsByRobotApartmentComplexIdAndStatusIn(
                        eq(2L),
                        argThat(
                                statuses ->
                                        statuses.contains(PatrolStatus.IN_PROGRESS)
                                                && statuses.contains(PatrolStatus.STOP_REQUESTED))))
                .thenReturn(false);

        assertThatCode(() -> new NavigationConfigurationGuard(patrolRepository).assertMutable(2L))
                .doesNotThrowAnyException();
    }

    @Test
    void rejectsConfigurationChangeWhilePatrolIsActive() {
        when(patrolRepository.existsByRobotApartmentComplexIdAndStatusIn(
                        eq(2L), argThat(statuses -> statuses.contains(PatrolStatus.IN_PROGRESS))))
                .thenReturn(true);

        assertThatThrownBy(
                        () -> new NavigationConfigurationGuard(patrolRepository).assertMutable(2L))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        exception ->
                                assertThat(exception.getErrorCode())
                                        .isEqualTo(ErrorCode.MAP_CONFIGURATION_LOCKED));
    }
}
