# AIoT infrastructure

This directory contains the single-EC2 runtime and GitLab CI/CD skeleton.

Start with [CICD_V2_OPERATIONS.md](CICD_V2_OPERATIONS.md) for the implemented
part-master release flow, rollout order, candidate integration gates, release
manifest, and component rollback. [CICD_MIGRATION_HANDOFF.md](CICD_MIGRATION_HANDOFF.md)
preserves the approved design and [OPERATIONS.md](OPERATIONS.md) contains the
single-EC2 runtime, backup, MQTT, and certificate procedures.

## Runtime

- Host Nginx terminates HTTPS and proxies `/` to the frontend and `/api/` to Spring.
- MySQL and Mosquitto run in `compose.infrastructure.yaml`.
- Frontend and backend run in `compose.application.yaml` after their Dockerfiles exist.
- Jetson connects to Mosquitto with TLS on port 8883.
- Port 1883 is private to the `aiot-network` Docker network in the final configuration.

## Branch flow

```text
feature -> part/dev -> part/master -> develop -> root master
```

The part-master release flow is active. `front/master` and `back/master` run
candidate integration and deploy only their own application component.
`develop` records an approved component combination and does not deploy EC2;
root `master` is a manually approved final milestone. Follow
[CICD_V2_OPERATIONS.md](CICD_V2_OPERATIONS.md) for daily use.
Robot uses an approved-release Pull OTA flow. CI packages only an `iot-vX.Y.Z`
tag whose commit belongs to `iot/master`; a protected manual job publishes the
immutable Robot-only archive and stable manifest. The Jetson validates the AI
ROS contract, architecture, checksum, and stationary smoke test before an atomic
switch, with offline fallback and rollback. The existing AI runtime stays under
`/home/e103/yolo-pipeline` and is managed independently by `aiot-ai.service`.
See [jetson/README.md](jetson/README.md) and [GPU_RUNNER.md](GPU_RUNNER.md).

## Secrets

Real secrets live only under `/srv/aiot/secrets`. Never commit `.env`, certificates, runner tokens, or passwords.
The Mattermost incoming webhook is stored only as the protected and masked
GitLab CI/CD variable `MM_WEBHOOK_URL`.

## Deployment notifications

`front/master` and `back/master` deployments run through
`scripts/deploy-with-notification.sh`. It posts a custom card to the channel
configured by the Mattermost incoming webhook:

- green: deployment and health verification completed;
- yellow: candidate integration failed, so production was not changed;
- orange: deployment failed but the previous component was restored;
- red with `@channel`: deployment failed and either rollback was unavailable
  or rollback also failed.
- blue: a protected Jetson IoT release was published.

The headings use the Mattermost custom emoji names
`:small_green_circle:`, `:small_orange_circle:`, `:small_red_circle:`,
`:small_yellow_circle:`, and `:small_blue_circle:`.

The card contains the triggering user, changed commit/file counts, completion
time, elapsed time, and service link. Notification delivery is best effort:
Mattermost downtime never changes an otherwise successful deployment result.
`scripts/test-notify-mattermost.sh` validates the rendered payload without
contacting Mattermost or exposing the webhook URL.
When notification files change on `infra/dev`, the
`mattermost_notification_smoke` job is available as an optional manual
connection test. It never posts automatically.

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
