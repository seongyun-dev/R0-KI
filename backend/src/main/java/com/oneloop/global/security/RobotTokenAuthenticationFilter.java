package com.oneloop.global.security;

import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.repository.RobotRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

// 로봇이 REST API(이벤트생성/증거업로드 등)를 호출할 때 쓰는 인증 필터.
// 관리자 JWT랑 똑같이 Authorization: Bearer 헤더를 쓰지만, 값 자체는 로그인 토큰이 아니라
// 로봇 등록 시 발급한 서비스 토큰(DB의 service_token 컬럼)이라 별도 필터로 검증한다.
// SecurityConfig에서 이 필터를 JwtAuthenticationFilter보다 먼저 실행하도록 등록한다.
@Component
@RequiredArgsConstructor
public class RobotTokenAuthenticationFilter extends OncePerRequestFilter {

    private static final String AUTHORIZATION_HEADER = "Authorization";
    private static final String BEARER_PREFIX = "Bearer ";

    private final RobotRepository robotRepository;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String token = resolveToken(request);

        // 토큰이 없거나, 있어도 로봇 토큰이 아니면(DB에 없으면) 그냥 다음 필터로 넘김 -
        // 뒤에 오는 JwtAuthenticationFilter가 "관리자 JWT인지"를 이어서 검사하게 됨
        if (StringUtils.hasText(token)) {
            Optional<PatrolRobot> robot = robotRepository.findByServiceToken(token);
            robot.ifPresent(this::authenticateAsRobot);
        }
        filterChain.doFilter(request, response);
    }

    // ROLE_ROBOT 권한으로 SecurityContext에 인증을 세팅한다. principal은 관리자처럼 회원 정보가 아니라 로봇 ID.
    private void authenticateAsRobot(PatrolRobot robot) {
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                robot.getId(), null, List.of(new SimpleGrantedAuthority("ROLE_ROBOT"))));
    }

    private String resolveToken(HttpServletRequest request) {
        String authorization = request.getHeader(AUTHORIZATION_HEADER);
        if (StringUtils.hasText(authorization) && authorization.startsWith(BEARER_PREFIX)) {
            return authorization.substring(BEARER_PREFIX.length());
        }
        return null;
    }
}
