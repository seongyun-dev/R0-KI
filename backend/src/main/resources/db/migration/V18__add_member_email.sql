-- 회원 이메일 추가.
-- 이미 가입된 회원에게는 이메일이 없으므로 NULL 을 허용한다.
-- UNIQUE 는 NULL 을 중복으로 보지 않아 기존 행과 충돌하지 않는다.
ALTER TABLE members
    ADD COLUMN email VARCHAR(255);

ALTER TABLE members
    ADD CONSTRAINT uk_members_email UNIQUE (email);
