package com.oneloop.auth.service;

import com.oneloop.apartment.domain.ApartmentComplex;
import com.oneloop.apartment.repository.ApartmentComplexRepository;
import com.oneloop.auth.dto.ApartmentRequest;
import com.oneloop.auth.dto.CurrentMemberResponse;
import com.oneloop.auth.dto.SigninRequest;
import com.oneloop.auth.dto.SigninResponse;
import com.oneloop.auth.dto.SignupRequest;
import com.oneloop.auth.dto.SignupResponse;
import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.global.security.JwtTokenProvider;
import com.oneloop.map.repository.PatrolMapRepository;
import com.oneloop.member.domain.Member;
import com.oneloop.member.domain.MemberStatus;
import com.oneloop.member.repository.MemberRepository;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.repository.RobotRepository;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AuthService {

    private final MemberRepository memberRepository;
    private final ApartmentComplexRepository apartmentComplexRepository;
    private final RobotRepository robotRepository;
    private final PatrolMapRepository patrolMapRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;

    @Transactional
    public SignupResponse signup(SignupRequest request) {
        if (memberRepository.existsByUsername(request.getUsername())) {
            throw new BusinessException(ErrorCode.DUPLICATE_USERNAME);
        }

        ApartmentRequest apartmentRequest = request.getApartment();
        ApartmentComplex apartmentComplex =
                apartmentComplexRepository
                        .findByNameAndPostalCodeAndAddress(
                                apartmentRequest.getName(),
                                apartmentRequest.getPostalCode(),
                                apartmentRequest.getAddress())
                        .orElse(null);

        boolean isNewApartment = apartmentComplex == null;
        if (isNewApartment) {
            apartmentComplex =
                    apartmentComplexRepository.save(
                            new ApartmentComplex(
                                    apartmentRequest.getName(),
                                    apartmentRequest.getAddress(),
                                    apartmentRequest.getPostalCode()));
        }

        Member member =
                Member.create(
                        apartmentComplex,
                        request.getUsername(),
                        request.getPassword(),
                        request.getName(),
                        request.getPhoneNumber(),
                        passwordEncoder);
        memberRepository.save(member);

        String accessToken =
                jwtTokenProvider.createAccessToken(
                        member.getId().toString(), apartmentComplex.getId(), List.of());
        return new SignupResponse(isNewApartment, accessToken);
    }

    /**
     * 아이디와 비밀번호로 사용자를 인증하고, 사용자 식별자를 subject로 갖는 Access Token을 발급한다.
     *
     * @param request 로그인 아이디와 비밀번호
     * @return 발급된 Access Token
     * @throws BusinessException 계정이 없거나 비밀번호가 일치하지 않거나 계정이 비활성 상태인 경우
     */
    public SigninResponse signin(SigninRequest request) {
        Member member =
                memberRepository
                        .findByUsername(request.getUsername())
                        .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_CREDENTIALS));

        if (!passwordEncoder.matches(request.getPassword(), member.getPassword())) {
            throw new BusinessException(ErrorCode.INVALID_CREDENTIALS);
        }
        if (member.getStatus() != MemberStatus.ACTIVE) {
            throw new BusinessException(ErrorCode.MEMBER_NOT_ACTIVE);
        }

        Long apartmentComplexId = member.getApartmentComplex().getId();
        String accessToken =
                jwtTokenProvider.createAccessToken(
                        member.getId().toString(), apartmentComplexId, List.of());
        boolean hasRobot =
                robotRepository.countByApartmentComplexIdAndStatusNot(
                                apartmentComplexId, RobotStatus.DELETED)
                        > 0;
        boolean hasMap = patrolMapRepository.findByApartmentComplexId(apartmentComplexId).isPresent();
        return new SigninResponse(accessToken, member.getName(), hasRobot, hasMap);
    }

    /**
     * JWT로 인증된 사용자 식별자를 이용해 현재 로그인한 사용자 정보를 조회한다.
     *
     * @param memberId JWT subject에서 추출한 사용자 식별자
     * @return 현재 로그인한 사용자 정보
     * @throws BusinessException 사용자 식별자에 해당하는 회원이 존재하지 않는 경우
     */
    public CurrentMemberResponse getCurrentMember(Long memberId) {
        Member member =
                memberRepository
                        .findById(memberId)
                        .orElseThrow(() -> new BusinessException(ErrorCode.UNAUTHORIZED));
        return CurrentMemberResponse.from(member);
    }
}
