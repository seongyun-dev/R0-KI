# AIoT 인프라 운영 가이드

현재 EC2 런타임, 파트별 master 배포, 후보 통합검사, Release Manifest와 파트별 롤백이 활성화되어 있다. 브랜치 작업 순서는 [CICD_V2_OPERATIONS.md](CICD_V2_OPERATIONS.md)를 따른다. `develop`은 검증된 조합을 기록할 뿐 운영 서버를 다시 배포하지 않는다.

## 1. 운영 구조

```text
인터넷 사용자
  └─ HTTPS 443 -> EC2 Nginx
                    ├─ /      -> Frontend 127.0.0.1:3000
                    └─ /api/  -> Backend  127.0.0.1:8080

Jetson
  └─ MQTT TLS 8883 -> aiot-mosquitto

Docker aiot-network
  ├─ aiot-mysql:3306      (호스트에서는 127.0.0.1:3306만 공개)
  ├─ aiot-mosquitto:1883  (Backend 전용)
  ├─ aiot-mosquitto:8883  (Jetson TLS)
  ├─ aiot-backend
  └─ aiot-frontend
```

Gerrit(8988/29418)과 Apache(8989)는 별도 서비스다. AIoT 장애 대응 중에도 중지하거나 설정을 변경하지 않는다.

## 2. 서버 주요 경로

| 경로 | 용도 |
| --- | --- |
| `/srv/aiot/compose` | 운영 Docker Compose 파일 |
| `/srv/aiot/config` | Nginx·Mosquitto 설정 |
| `/srv/aiot/certs/mqtt` | Mosquitto 인증서 사본 |
| `/srv/aiot/data` | MySQL·MQTT·업로드·지도 영속 데이터 |
| `/srv/aiot/secrets` | 운영 비밀값. 커밋·출력 금지 |
| `/srv/aiot/deploy` | 배포·헬스체크·롤백 스크립트와 현재 상태 |
| `/srv/aiot/backups/runtime` | 일일 로컬 백업 |
| `/srv/aiot/releases/jetson/iot/stable` | 공개 가능한 Robot stable manifest |

Jetson용 MQTT 파일은 `/srv/aiot/secrets/robot-mqtt.env`에 있다. 인증된 전달 경로만 사용한다.

## 3. CI/CD 동작

```text
front/dev -> front/master -> 후보 통합검사 -> Front만 EC2 배포
back/dev  -> back/master  -> 후보 통합검사 -> Back만 EC2 배포

배포 성공한 파트 버전 조합 -> develop 기록 -> 최상위 master 수동 승인

iot/master -> iot-vX.Y.Z -> 패키지 자동 생성
                         -> iot_publish 수동 승인
                         -> Jetson이 부팅할 때 Pull
```

- 파트 `dev`는 CI만 수행한다.
- Front와 Back은 서로 독립적으로 배포하고 독립적으로 롤백할 수 있다.
- `develop`에 merge했다고 EC2가 다시 배포되지는 않는다.
- Jetson 릴리스는 merge 배포와 분리되어 있다.
- 서버 Runner는 `aiot-ec2` 태그, Shell executor, 동시 실행 1개, 최대 30분으로 운영한다.
- Runner의 Docker 권한은 사실상 호스트 root 권한이므로 이 프로젝트에만 잠그고 untagged job을 허용하지 않는다.

## 4. 일상 점검 명령

```bash
# 전체 인프라 헬스체크
sudo /srv/aiot/deploy/health-check.sh infrastructure

# Front/Back 애플리케이션 헬스체크
sudo /srv/aiot/deploy/health-check.sh application frontend backend

# 컨테이너 상태
sudo docker compose \
  --env-file /srv/aiot/secrets/runtime.env \
  -f /srv/aiot/compose/compose.infrastructure.yaml ps
sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# 최근 로그
sudo docker logs --tail 100 aiot-backend
sudo docker logs --tail 100 aiot-frontend
sudo docker logs --tail 100 aiot-mysql
sudo docker logs --tail 100 aiot-mosquitto

# 수동 백업과 결과
sudo systemctl start aiot-backup.service
sudo journalctl -u aiot-backup.service -n 100 --no-pager
systemctl list-timers aiot-backup.timer

# 주기 모니터링과 최근 결과
sudo systemctl start aiot-monitor.service
sudo journalctl -u aiot-monitor.service -n 100 --no-pager
systemctl list-timers aiot-monitor.timer
```

백업에는 체크섬, `COMPLETED` 표시, 메타데이터와 원자적으로 교체되는 `latest` 링크가 포함된다. 7일이 지난 백업은 목록만 표시하고 자동 삭제하지 않는다. 같은 EC2 디스크에 있으므로 인스턴스·볼륨 장애까지 대비하려면 별도 암호화 저장소가 필요하다.

## 5. MySQL 접속

MySQL 3306은 EC2 loopback에만 공개한다. AWS Security Group이나 UFW에 외부 3306 허용 규칙을 추가하지 않는다.

MySQL Workbench에서는 `Standard TCP/IP over SSH`를 사용한다.

| 항목 | 값 |
| --- | --- |
| SSH hostname | `i15e103.p.ssafy.io:22` |
| SSH username | `ubuntu` |
| SSH key | 담당자 PC의 `I15E103T.pem` |
| MySQL hostname | `127.0.0.1` |
| MySQL port | `3306` |
| MySQL username | `root` |

`MYSQL_ROOT_PASSWORD`는 승인된 비밀 공유 절차로만 확인한다. root 계정은 전체 테이블을 변경·삭제할 수 있으므로 운영 점검 외에는 사용하지 않는다.

## 6. Front·Back 배포 확인

1. GitLab에서 해당 파트 master 파이프라인이 성공했는지 확인한다.
2. Mattermost의 초록 배포 완료 카드를 확인한다.
3. EC2에서 `current.env`와 컨테이너 이미지를 확인한다.
4. 헬스체크와 실제 URL을 확인한다.

```bash
sudo sed -n 's/=.*$/=<configured>/p' /srv/aiot/deploy/current.env
sudo docker inspect aiot-frontend aiot-backend \
  --format '{{.Name}} {{.Config.Image}} {{.State.Status}}'
sudo /srv/aiot/deploy/health-check.sh application frontend backend
```

Backend가 Actuator를 제공하면 readiness를 `/actuator/health`로 전환한다. 그 전에는 `/swagger-ui.html`을 fallback으로 사용한다.

## 7. Jetson 릴리스

자세한 절차는 [jetson/README.md](jetson/README.md)를 따른다.

1. Robot 코드를 `iot/master`에 merge한다.
2. 이전 태그보다 높은 `iot-vX.Y.Z` 태그를 생성하고 원격에 push한다.
3. GitLab의 `iot_package` 성공을 확인한다.
4. 같은 파이프라인의 `iot_publish`를 수동 실행한다.
5. stable manifest의 `release`가 새 버전인지 확인한다.
6. Jetson에서 updater를 실행하고 현재 버전을 확인한다.

```bash
# 개발자 PC
git fetch origin --tags
git switch iot/master
git pull --ff-only origin iot/master
git tag -a iot-v0.1.2 -m "iot v0.1.2"
git push origin iot-v0.1.2

# 게시 완료 확인
curl -fsS https://i15e103.p.ssafy.io/jetson/releases/iot/stable/manifest.json

# Jetson 수동 pull
sudo systemctl stop aiot-robot.service
sudo systemctl restart aiot-update.service
sudo journalctl -u aiot-update.service -n 100 --no-pager
cat /opt/aiot/iot/state/VERSION
readlink -f /opt/aiot/iot/current
```

보호 태그 `iot-v*`는 현재 Developer와 Maintainer가 생성할 수 있다. `git tag`만 실행하면 로컬 태그일 뿐이며 `git push origin <태그>`까지 해야 GitLab 파이프라인이 시작된다. `jetson-v*`, `v1.0.0` 등 다른 이름은 현재 규칙과 일치하지 않는다.

## 8. Jetson 실패 정책

다음 오류에서는 설치 중인 후보를 버리고 마지막 정상 Robot 릴리스를 유지한다.

- 네트워크 또는 manifest 다운로드 실패
- 잘못된 manifest 스키마
- AI 계약·JetPack·CPU 아키텍처 불일치
- 허용하지 않은 artifact 주소
- 파일 크기·SHA-256·내부 체크섬 불일치
- 위험한 압축 경로 또는 AI 모델 포함
- 설치·무구동 smoke 실패

`aiot-robot.service`는 AI를 `Wants/After`로만 참조한다. AI 장애로 Robot 프로세스까지 강제 종료하지 않고 LIMITED 모드로 남긴다. IoT OTA는 AI venv, 모델, TensorRT engine, 로그와 evidence를 변경하지 않는다.

## 9. MQTT 이전

기존 `hanbakwi-mosquitto`의 익명 1883은 이전 기간에만 유지한다.

1. Jetson을 `i15e103.p.ssafy.io:8883` TLS 계정으로 연결한다.
2. 명령·상태 통신과 재연결을 검증한다.
3. 검증 후에만 `hanbakwi-mosquitto`를 중지·비활성화한다.
4. 외부 1883이 더 이상 열리지 않았는지 확인한다.
5. AWS Security Group에서 8883의 출발지 범위를 점검한다.

Docker publish 포트는 UFW 전달 규칙을 우회할 수 있으므로 UFW만 보고 안전하다고 판단하지 않는다.

## 10. TLS 인증서 갱신

현재 wildcard 인증서는 수동 DNS 검증 방식이다. 인증서 발급 자체는 자동화되지 않았으며, 성공적으로 갱신된 인증서를 Nginx와 Mosquitto에 반영하는 deploy hook만 설치되어 있다.

만료 전에 수동 갱신한 뒤 실행한다.

```bash
sudo /srv/aiot/deploy/sync-certificates.sh
sudo /srv/aiot/deploy/health-check.sh infrastructure
```

## 11. 롤백 경계

애플리케이션 롤백은 이전 Front 또는 Back 이미지와 Compose 상태를 복원한다. MySQL·업로드 파일 복원은 현재 데이터를 덮어쓰므로 자동화하지 않는다. `/srv/aiot/backups/runtime`에서 검증된 백업을 선택하고 체크섬과 영향 범위를 확인한 뒤 수동 복원한다.
