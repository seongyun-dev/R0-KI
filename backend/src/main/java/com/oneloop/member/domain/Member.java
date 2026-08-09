package com.oneloop.member.domain;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.global.common.BaseEntity;
import jakarta.persistence.*;
import lombok.*;
import org.springframework.security.crypto.password.PasswordEncoder;

@Getter
@Entity
@Table(name = "members")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Member extends BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "member_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "apartment_complex_id", nullable = false)
    private ApartmentComplex apartmentComplex;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(nullable = false, length = 255)
    private String password;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(name = "phone_number", nullable = false, length = 20)
    private String phoneNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "member_status", nullable = false, length = 20)
    private MemberStatus status = MemberStatus.ACTIVE;

    private Member(
            ApartmentComplex apartmentComplex,
            String username,
            String encodedPassword,
            String name,
            String phoneNumber) {
        this.apartmentComplex = apartmentComplex;
        this.username = username;
        this.password = encodedPassword;
        this.name = name;
        this.phoneNumber = phoneNumber;
    }

    public static Member create(
            ApartmentComplex apartmentComplex,
            String username,
            String rawPassword,
            String name,
            String phoneNumber,
            PasswordEncoder passwordEncoder) {
        return new Member(
                apartmentComplex, username, passwordEncoder.encode(rawPassword), name, phoneNumber);
    }

    public void changePassword(String rawPassword, PasswordEncoder passwordEncoder) {
        this.password = passwordEncoder.encode(rawPassword);
    }

    public void suspend() {
        this.status = MemberStatus.SUSPENDED;
    }

    public void withdraw() {
        this.status = MemberStatus.WITHDRAWN;
    }
}
