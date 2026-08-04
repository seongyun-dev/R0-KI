package com.oneloop.mapping.repository;

import com.oneloop.mapping.domain.MappingSession;
import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MappingSessionRepository extends JpaRepository<MappingSession, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            "select session from MappingSession session "
                    + "join fetch session.apartmentComplex "
                    + "join fetch session.robot "
                    + "where session.apartmentComplex.id = :apartmentComplexId "
                    + "or session.robot.id = :robotId")
    Collection<MappingSession> findForUpdateByApartmentComplexIdOrRobotId(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("robotId") Long robotId);

    // commandId로 ACK가 어느 세션에 대한 응답인지 특정할 수 있다.
    Optional<MappingSession> findByCommandId(String commandId);

    Optional<MappingSession> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            "select session from MappingSession session "
                    + "join fetch session.robot "
                    + "where session.id = :id and session.commandId = :commandId")
    Optional<MappingSession> findForUpdateByIdAndCommandId(
            @Param("id") Long id, @Param("commandId") String commandId);
}
