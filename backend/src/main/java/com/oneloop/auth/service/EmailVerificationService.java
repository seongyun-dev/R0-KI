package com.oneloop.auth.service;

import com.oneloop.global.exception.BusinessException;
import com.oneloop.global.exception.ErrorCode;
import com.oneloop.member.repository.MemberRepository;
import java.security.SecureRandom;
import java.time.Duration;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

/** 회원가입용 이메일 인증 — 인증번호 발송과 확인을 담당한다. */
@Slf4j
@Service
@RequiredArgsConstructor
public class EmailVerificationService {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final MemberRepository memberRepository;
    private final EmailVerificationStore verificationStore;
    private final JavaMailSender mailSender;

    @Value("${app.email-verification.code-length:6}")
    private int codeLength;

    @Value("${app.email-verification.ttl-minutes:5}")
    private int ttlMinutes;

    @Value("${app.email-verification.from:no-reply@oneloop.local}")
    private String from;

    /**
     * 인증번호를 발송한다.
     *
     * @throws BusinessException 이미 가입된 이메일이면 발송하지 않고 EMAIL_ALREADY_EXISTS
     */
    public void send(String email) {
        String normalized = normalize(email);
        if (memberRepository.existsByEmail(normalized)) {
            throw new BusinessException(ErrorCode.EMAIL_ALREADY_EXISTS);
        }

        String code = generateCode();
        verificationStore.save(normalized, code, Duration.ofMinutes(ttlMinutes));
        sendMail(normalized, code);
    }

    /**
     * 인증번호를 확인하고 인증 완료로 표시한다.
     *
     * @throws BusinessException 번호가 틀리거나 만료됐으면 INVALID_EMAIL_VERIFICATION_CODE
     */
    public void verify(String email, String code) {
        if (!verificationStore.verify(normalize(email), code)) {
            throw new BusinessException(ErrorCode.INVALID_EMAIL_VERIFICATION_CODE);
        }
    }

    /**
     * 회원가입 시점에 이 주소가 인증을 마쳤는지 확인한다.
     *
     * @throws BusinessException 인증 전이면 EMAIL_NOT_VERIFIED
     */
    public void assertVerified(String email) {
        if (!verificationStore.isVerified(normalize(email))) {
            throw new BusinessException(ErrorCode.EMAIL_NOT_VERIFIED);
        }
    }

    /** 가입에 사용한 인증은 재사용하지 못하도록 지운다. */
    public void consume(String email) {
        verificationStore.remove(normalize(email));
    }

    /** 저장·조회 키와 회원 레코드가 어긋나지 않도록 한 곳에서 정규화한다. */
    public String normalize(String email) {
        return email == null ? "" : email.trim().toLowerCase();
    }

    private String generateCode() {
        StringBuilder code = new StringBuilder(codeLength);
        for (int i = 0; i < codeLength; i++) {
            code.append(RANDOM.nextInt(10));
        }
        return code.toString();
    }

    private void sendMail(String email, String code) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(email);
        message.setSubject("[R0-Ki] 이메일 인증번호");
        message.setText(
                """
                안녕하세요. R0-Ki 입니다.

                아래 인증번호를 입력해 이메일 인증을 완료해 주세요.

                인증번호: %s

                인증번호는 발송 시각으로부터 %d분간 유효합니다.
                본인이 요청하지 않았다면 이 메일은 무시하셔도 됩니다.
                """
                        .formatted(code, ttlMinutes));
        try {
            mailSender.send(message);
        } catch (Exception exception) {
            // 발송에 실패했는데 번호만 남아 있으면 사용자가 영영 확인할 수 없다
            verificationStore.remove(email);
            log.warn("[EMAIL] 인증번호 발송에 실패했습니다. email={}", email, exception);
            throw new BusinessException(ErrorCode.EMAIL_SEND_FAILED);
        }
    }
}
