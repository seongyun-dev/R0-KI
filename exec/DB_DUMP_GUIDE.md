# DB 덤프 및 복원 가이드

확인 기준: 2026-08-10

## 1. 덤프 파일

| 항목 | 값 |
| --- | --- |
| 파일 | `exec/db/aiot_db_20260810.sql` |
| DBMS | MySQL 8.4 |
| Database | `aiot` |
| 애플리케이션 테이블 | 19개 |
| Flyway 적용 버전 | V1~V18 |
| SHA-256 | `1b08f8eddcbea42443d1d4c17c5a50f6287ebbc1cc2539885d11ce11bb0b029c` |

운영 DB를 `--single-transaction`으로 복제한 뒤 제출용 임시 DB에서 비식별화했다. 운영 DB는 변경하지 않았다. 수동으로 만든 `*_backup*` 테이블은 애플리케이션 스키마가 아니므로 덤프에서 제외했다.

주요 데이터 건수는 다음과 같다.

| 테이블 | 건수 |
| --- | ---: |
| `members` | 19 |
| `residents` | 5 |
| `registered_vehicles` | 4 |
| `patrol_robots` | 31 |
| `patrols` | 418 |
| `detected_events` | 491 |
| `route_positions` | 3,762 |
| `flyway_schema_history` | 18 |

## 2. 비식별화 내용

- 회원 ID, 이름, 이메일과 전화번호를 제출용 값으로 변경
- 모든 회원 비밀번호를 제출용 공통 비밀번호로 변경
- 입주민 이름, 전화번호와 동·호수 변경
- 차량번호와 인식 차량번호 변경
- Robot serial과 service token 제거 또는 변경
- 알림, 처리 기록, AI 요약과 이벤트 상세 내용 변경
- 증거 파일 URL을 제출용 경로로 변경
- 아파트 이름, 주소와 우편번호 변경

원본 운영 비밀번호, JWT, MQTT 계정, API Key는 덤프에 포함되지 않는다.

## 3. 제출용 로그인 계정

복원된 DB에서는 다음 형식의 계정을 사용할 수 있다.

```text
아이디: demo_member_1 ~ demo_member_19
비밀번호: R0ki!2026
상태: ACTIVE
```

이 계정은 제출용 DB에서만 사용한다. 운영 DB의 계정과 비밀번호는 변경되지 않았다.

## 4. Docker로 복원

기존 운영 DB가 아닌 빈 MySQL에 복원한다.

```bash
docker run -d \
  --name aiot-db-restore \
  -e MYSQL_ROOT_PASSWORD=local-root-password \
  -e MYSQL_DATABASE=aiot \
  -p 3307:3306 \
  mysql:8.4
```

MySQL이 준비된 뒤 덤프를 넣는다.

```bash
docker exec -i aiot-db-restore \
  mysql -uroot -plocal-root-password aiot \
  < exec/db/aiot_db_20260810.sql
```

PowerShell에서는 다음과 같이 실행한다.

```powershell
cmd /c "docker exec -i aiot-db-restore mysql -uroot -plocal-root-password aiot < exec\db\aiot_db_20260810.sql"
```

## 5. 복원 확인

```bash
docker exec aiot-db-restore \
  mysql -uroot -plocal-root-password -D aiot \
  -e "SELECT COUNT(*) AS tables_count FROM information_schema.tables WHERE table_schema='aiot';"

docker exec aiot-db-restore \
  mysql -uroot -plocal-root-password -D aiot \
  -e "SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;"
```

예상 결과는 테이블 19개, Flyway V1~V18 모두 `success=1`이다. 생성된 덤프는 별도 빈 DB에 실제로 복원한 뒤 원본 제출용 DB와 모든 테이블의 행 수가 같은 것을 확인했다.

## 6. Backend 연결

Backend에는 다음 환경변수를 지정한다.

```env
SPRING_DATASOURCE_URL=jdbc:mysql://aiot-db-restore:3306/aiot?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Seoul
SPRING_DATASOURCE_USERNAME=root
SPRING_DATASOURCE_PASSWORD=local-root-password
```

Docker 네트워크 밖에서 실행하면 Host를 `127.0.0.1`, Port를 `3307`로 바꾼다. 실제 운영에서는 root 대신 `aiot_app` 전용 계정을 사용한다.

## 7. 주의사항

- 이 덤프는 `DROP TABLE IF EXISTS`를 포함하므로 운영 DB에 직접 실행하지 않는다.
- 운영 복구는 `/srv/aiot/backups/runtime/`의 검증된 백업을 사용한다.
- 데이터가 변경되면 최신 덤프를 다시 만들고 파일명, 기준일과 SHA-256을 갱신한다.
- 파일 업로드, 지도, 이벤트 증거 원본은 DB 덤프에 포함되지 않는다.
- Robot service token은 제거되어 있으므로 실제 장비 연결 시 새 토큰을 발급해야 한다.
