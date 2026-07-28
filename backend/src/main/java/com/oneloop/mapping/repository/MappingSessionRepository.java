package com.oneloop.mapping.repository;

import com.oneloop.mapping.domain.MappingSession;
import com.oneloop.mapping.domain.MappingStatus;
import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MappingSessionRepository extends JpaRepository<MappingSession, Long> {

    // 같은 로봇에 진행 중인 지도 생성 세션이 존재하는지 검사한다.
    boolean existsByRobotIdAndStatusIn(Long robotId, Collection<MappingStatus> statuses);

    boolean existsByApartmentComplexIdOrRobotId(Long apartmentComplexId, Long robotId);

    // IoT ACK가 백엔드에서 발행한 세션과 명령 모두에 해당하는지 확인한다.
    Optional<MappingSession> findByIdAndCommandId(Long id, String commandId);

    Optional<MappingSession> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            "select session from MappingSession session "
                    + "join fetch session.robot "
                    + "where session.id = :id and session.commandId = :commandId")
    Optional<MappingSession> findForUpdateByIdAndCommandId(
            @Param("id") Long id, @Param("commandId") String commandId);
}
