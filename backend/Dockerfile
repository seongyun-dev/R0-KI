FROM eclipse-temurin:21-jdk-jammy AS builder

WORKDIR /workspace

COPY gradlew ./gradlew
COPY gradle ./gradle
COPY settings.gradle* build.gradle* ./
RUN chmod +x ./gradlew

COPY src ./src
RUN set -eux; \
    ./gradlew --no-daemon clean bootJar; \
    jar_file="$(find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' -print -quit)"; \
    test -n "${jar_file}"; \
    cp "${jar_file}" /workspace/app.jar

FROM eclipse-temurin:21-jre-jammy

RUN groupadd --system --gid 10001 aiot \
    && useradd --system --uid 10001 --gid aiot --home-dir /app --shell /usr/sbin/nologin aiot

WORKDIR /app
RUN install -d -o aiot -g aiot /app/data/uploads /app/data/maps

COPY --from=builder --chown=aiot:aiot /workspace/app.jar /app/app.jar

USER aiot
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
