package com.oneloop.auth.service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 이메일 인증번호 보관소.
 *
 * <p>메모리에 들고 있으므로 서버를 재시작하면 진행 중이던 인증은 사라진다. 인스턴스를 여러 대로 늘리면 발송한 서버와 확인하는 서버가 달라져 동작하지 않는다. 그때는
 * Redis 같은 외부 저장소로 옮겨야 한다 — 지금은 단일 인스턴스 기준이다.
 */
@Component
public class EmailVerificationStore {

    /** 인증 완료 상태를 회원가입까지 들고 있는 시간. 코드 유효시간과는 별개다. */
    private static final Duration VERIFIED_TTL = Duration.ofMinutes(30);

    private final Map<String, Entry> entries = new ConcurrentHashMap<>();

    private record Entry(String code, LocalDateTime expiresAt, boolean verified) {
        private boolean isExpired(LocalDateTime now) {
            return expiresAt.isBefore(now);
        }
    }

    /** 발송한 인증번호를 저장한다. 같은 주소로 다시 보내면 이전 번호는 무효가 된다. */
    public void save(String email, String code, Duration ttl) {
        entries.put(key(email), new Entry(code, LocalDateTime.now().plus(ttl), false));
    }

    /**
     * 인증번호가 맞으면 인증 완료로 표시하고 true 를 돌려준다.
     *
     * <p>번호가 없거나 만료됐거나 틀리면 false 다.
     */
    public boolean verify(String email, String code) {
        String key = key(email);
        Entry entry = entries.get(key);
        LocalDateTime now = LocalDateTime.now();
        if (entry == null || entry.isExpired(now) || !entry.code().equals(code)) {
            return false;
        }
        entries.put(key, new Entry(entry.code(), now.plus(VERIFIED_TTL), true));
        return true;
    }

    /** 회원가입 시점에 이 주소가 인증을 마친 상태인지 확인한다. */
    public boolean isVerified(String email) {
        Entry entry = entries.get(key(email));
        return entry != null && entry.verified() && !entry.isExpired(LocalDateTime.now());
    }

    /** 가입에 사용한 인증은 재사용하지 못하도록 지운다. */
    public void remove(String email) {
        entries.remove(key(email));
    }

    /** 남은 유효시간 — 안내 문구에만 쓴다. */
    public Optional<LocalDateTime> expiresAt(String email) {
        return Optional.ofNullable(entries.get(key(email))).map(Entry::expiresAt);
    }

    // 대소문자만 다른 주소를 다른 주소로 취급하지 않는다
    private String key(String email) {
        return email == null ? "" : email.trim().toLowerCase();
    }
}
