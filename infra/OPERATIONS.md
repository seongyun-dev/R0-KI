# AIoT operations runbook

## Deployed topology

```text
Internet / Jetson
  ├─ HTTPS 443 -> host Nginx -> frontend 127.0.0.1:3000
  │                         -> backend  127.0.0.1:8080
  └─ MQTT TLS 8883 -> aiot-mosquitto

Docker network: aiot-network
  ├─ aiot-mysql:3306       (not published to the host)
  ├─ aiot-mosquitto:1883   (backend-only listener)
  ├─ aiot-mosquitto:8883   (published for Jetson)
  ├─ aiot-backend          (added when its Dockerfile exists)
  └─ aiot-frontend         (added when its Dockerfile exists)
```

Gerrit on 8988/29418 and Apache on 8989 are unrelated services. Do not modify them.

## Server paths

| Path | Purpose |
| --- | --- |
| `/srv/aiot/compose` | Installed Compose definitions |
| `/srv/aiot/config` | Nginx and Mosquitto configuration |
| `/srv/aiot/certs/mqtt` | Mosquitto certificate copies |
| `/srv/aiot/data` | MySQL, MQTT, upload, and map data |
| `/srv/aiot/secrets` | Runtime credentials; never commit or print |
| `/srv/aiot/deploy` | Root-installed deployment scripts and state |
| `/srv/aiot/backups/runtime` | Daily local backups |

The Jetson connection file is `/srv/aiot/secrets/robot-mqtt.env`. Transfer it only through an authenticated channel after the Jetson address and account are confirmed.

## CI/CD flow

Part branches run validation and tests. Integration deployment comes only from `develop`; `master` deployment is manual.

```text
front/dev ─┐
back/dev  ─┼─> develop --automatic--> EC2
iot/dev   ─┤       └──> master --manual--> EC2
ai/dev    ─┤
infra/dev ─┘
```

The Jetson and AI model artifacts are not auto-deployed. Model conversion and Jetson installation remain a deliberate device-side operation.

The project runner uses the `aiot-ec2` tag, Shell executor, one concurrent job, and a 30-minute maximum job timeout. Because Docker group access is equivalent to host root access, keep the runner locked to this project, keep untagged jobs disabled, protect release branches, and require infrastructure review for `.gitlab-ci.yml` and `infra/**`.

GitLab CE is 18.11.5, so the server runner is pinned to the matching 18.11 line rather than the unrelated latest major version.

## Routine commands

```bash
# Overall health
sudo /srv/aiot/deploy/health-check.sh infrastructure

# Infrastructure status and logs
sudo docker compose \
  --env-file /srv/aiot/secrets/runtime.env \
  -f /srv/aiot/compose/compose.infrastructure.yaml ps
sudo docker logs --tail 100 aiot-mysql
sudo docker logs --tail 100 aiot-mosquitto

# Manual backup
sudo systemctl start aiot-backup.service
sudo journalctl -u aiot-backup.service -n 100 --no-pager

# Backup timer
systemctl list-timers aiot-backup.timer
```

Backups are currently on the same EC2 disk. They protect against bad deployments and accidental file changes, but not instance or volume loss. Add an external encrypted destination when AWS credentials or another backup target becomes available.

## Application activation

Do this only after both application Dockerfiles and the backend health endpoint exist.

1. Confirm the frontend build context is `frontend/` and the backend context is `backend/`.
2. The current fallback readiness URL is `/swagger-ui.html`. Replace it with `/actuator/health` after the backend adds Spring Boot Actuator and permits that endpoint.
3. Run an application deployment and verify ports 3000 and 8080 are loopback-only.
4. Run `sudo /srv/aiot/deploy/install-nginx.sh`.
5. Verify `https://i15e103.p.ssafy.io/infra-health`, the frontend, and `/api/`.

## MQTT migration

The old `hanbakwi-mosquitto` container on public anonymous port 1883 is intentionally retained during migration.

1. Configure Jetson with the secured robot account, hostname `i15e103.p.ssafy.io`, and TLS port 8883.
2. Verify authenticated command/status traffic and reconnect behavior.
3. Stop and disable only `hanbakwi-mosquitto`.
4. Verify host port 1883 is no longer listening externally.
5. Verify the AWS security group restricts 8883 to the required source network where possible.

Docker-published ports can bypass UFW forwarding rules, so do not treat a UFW rule alone as proof that 1883 or 8883 is filtered.

## TLS renewal

The wildcard certificate currently expires on 2026-09-21 04:14:15 UTC. Its Certbot profile uses manual DNS validation, so issuance is not fully automatic. The installed deploy hook copies a successfully renewed certificate to Mosquitto, restarts that broker, validates Nginx, and reloads Nginx.

Renew the wildcard certificate manually before expiry unless a DNS API hook is added, then run:

```bash
sudo /srv/aiot/deploy/sync-certificates.sh
sudo /srv/aiot/deploy/health-check.sh infrastructure
```

## Rollback boundary

Application rollback preserves the previous image variables and previous Compose file. Infrastructure data rollback is intentionally manual because restoring MySQL or uploaded files overwrites live data. Select a verified directory under `/srv/aiot/backups/runtime` and review its checksums before any restore.
