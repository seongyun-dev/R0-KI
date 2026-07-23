# AIoT operations runbook

> The EC2 runtime in this runbook is installed. The part-master pipeline, real
> candidate integration tests, JSON release manifest, and component rollback
> are active. Follow [CICD_V2_OPERATIONS.md](CICD_V2_OPERATIONS.md) for the
> release process. `develop` no longer deploys production.

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
| `/srv/aiot/releases/jetson/stable` | Public stable manifest only; artifacts remain private in GitLab |

The Jetson connection file is `/srv/aiot/secrets/robot-mqtt.env`. Transfer it only through an authenticated channel after the Jetson address and account are confirmed.

## CI/CD flow

Part dev branches run CI only. Each part master deploys only its own component.
`develop` records a verified multi-part combination without deploying it, and
root `master` remains a manually approved final milestone.

```text
front/dev -> front/master --automatic Front only--> EC2
back/dev  -> back/master  --automatic Back only----> EC2
verified part releases -> develop --no deployment--> root master --manual
```

Jetson release publishing is intentionally separate from merge deployment. A
`jetson-vX.Y.Z` tag creates a versioned Robot/AI bundle, and the protected
manual `jetson_publish` job uploads it to the Generic Package Registry and
atomically updates the public stable manifest. The device pulls and validates
the release at boot. See [jetson/](jetson/) and [HANDOFF.md](HANDOFF.md).

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

# Periodic monitor and recent result
systemctl list-timers aiot-monitor.timer
sudo systemctl start aiot-monitor.service
sudo journalctl -u aiot-monitor.service -n 100 --no-pager
```

Each completed backup contains checksums, a `COMPLETED` marker, metadata, and an
atomic `latest` symlink. Backups older than seven days are listed but never
deleted automatically. They remain on the same EC2 disk, so an external
encrypted destination is still required for instance or volume failure.

## Application activation

Each component can be activated independently after its source contract is complete.

1. Confirm the frontend build context is `frontend/` and the backend context is `backend/`.
2. The current fallback readiness URL is `/swagger-ui.html`. Replace it with `/actuator/health` after the backend adds Spring Boot Actuator and permits that endpoint.
3. Run an application deployment and verify ports 3000 and 8080 are loopback-only.
4. Run `sudo /srv/aiot/deploy/install-nginx.sh`.
5. Verify `https://i15e103.p.ssafy.io/infra-health`, the frontend, and `/api/`.

## GPU and Jetson release

The GPU project Runner uses tag `ai-gpu-device3`, has untagged jobs disabled,
and serializes work through the matching resource group. Installation and
environment detection are documented in [GPU_RUNNER.md](GPU_RUNNER.md).

Jetson release procedure:

1. Merge compatible AI and Robot code with their install/run/smoke contracts.
2. Create a protected `jetson-vX.Y.Z` tag.
3. Verify `jetson_package`, then manually approve `jetson_publish`.
4. Create a read-only Package Registry Deploy Token for the Jetson.
5. On the Jetson, create `/opt/aiot/secrets/package-read.env` and run
   `sudo bash infra/jetson/install.sh` from an authenticated source checkout.
6. Start `aiot-update.service`, verify `current`, `previous`, and `state/VERSION`,
   then start `aiot-robot.service`.

Do not install the updater until the device runtime entrypoint and its backup
have been confirmed. A missing network, invalid manifest, incompatible
JetPack/architecture, checksum failure, or smoke failure must leave the last
healthy release active.

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
