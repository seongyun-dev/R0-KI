# AIoT infrastructure

This directory contains the single-EC2 runtime and GitLab CI/CD skeleton.

Start with [HANDOFF.md](HANDOFF.md) for the exact completion state, remaining work, branch prerequisites, and the planned Jetson pull-update design. See [OPERATIONS.md](OPERATIONS.md) for routine deployment, migration, backup, and certificate procedures.

## Runtime

- Host Nginx terminates HTTPS and proxies `/` to the frontend and `/api/` to Spring.
- MySQL and Mosquitto run in `compose.infrastructure.yaml`.
- Frontend and backend run in `compose.application.yaml` after their Dockerfiles exist.
- Jetson connects to Mosquitto with TLS on port 8883.
- Port 1883 is private to the `aiot-network` Docker network in the final configuration.

## Branch flow

```text
front/dev ─┐
back/dev  ─┼→ develop → master
iot/dev   ─┤
ai/dev    ─┤
infra/dev ─┘
```

Part branches run CI. `develop` deploys automatically. `master` deployment is manual.
Robot and AI artifacts are not currently deployed automatically to Jetson. The planned next step is an approved-release Pull OTA flow: CI publishes only a tagged/manual Jetson bundle, and the Jetson checks and installs it at boot with offline fallback and rollback. See [HANDOFF.md](HANDOFF.md).

## Secrets

Real secrets live only under `/srv/aiot/secrets`. Never commit `.env`, certificates, runner tokens, or passwords.

## Server bootstrap order

1. Back up the existing Nginx and Mosquitto configuration.
2. Run `bootstrap-server.sh` as root.
3. Run `initialize-secrets.sh` as root.
4. Run `sync-certificates.sh` as root.
5. Run `deploy-infrastructure.sh`.
6. Verify MySQL and MQTT before enabling the Nginx application site.

The existing Gerrit (8988/29418) and Apache (8989) services are outside this project and must not be changed.

The existing anonymous broker on host port 1883 is kept only during migration. After the Jetson has been verified on TLS port 8883, stop the legacy `hanbakwi-mosquitto` container and remove its public 1883 exposure. Docker-published ports may bypass UFW, so verify the AWS security group as well.

The current wildcard certificate uses manual DNS validation. The deploy hook copies a successfully renewed certificate to MQTT and reloads Nginx, but certificate issuance itself still requires a manual renewal before expiry unless DNS API automation is added.
