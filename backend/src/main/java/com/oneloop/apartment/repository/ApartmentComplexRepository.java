package com.oneloop.apartment.repository;

import com.oneloop.apartment.domain.ApartmentComplex;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ApartmentComplexRepository extends JpaRepository<ApartmentComplex, Long> {
    Optional<ApartmentComplex> findByNameAndPostalCodeAndAddress(
            String name, String postalCode, String address);
}
