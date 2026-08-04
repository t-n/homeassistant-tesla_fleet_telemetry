ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23
ARG BUILD_VERSION
ARG BUILD_ARCH
ARG FLEET_TELEMETRY_REF=4767414c1297c8db37a082561c2b761ce8613590
ARG VEHICLE_COMMAND_REF=f97fa1e4bf617a364c72b85cb5d859528abeda67

# fleet-telemetry @ FLEET_TELEMETRY_REF requires go >= 1.26
FROM golang:1.26-alpine AS fleet_telemetry_build
# ARG defaults from before FROM are not inherited into stages; re-declare.
ARG FLEET_TELEMETRY_REF

WORKDIR /build

RUN apk add --no-cache \
    build-base \
    ca-certificates \
    git \
    libsodium-dev \
    make \
    pkgconf \
    zeromq-dev

WORKDIR /go/src/fleet-telemetry

RUN git clone https://github.com/teslamotors/fleet-telemetry.git . \
    && git checkout "${FLEET_TELEMETRY_REF}" \
    && export CGO_ENABLED=1 \
    && export CGO_LDFLAGS="-lstdc++" \
    && make

FROM golang:1.23-alpine AS vehicle_command_build
ARG VEHICLE_COMMAND_REF

WORKDIR /app

RUN apk add --no-cache \
    ca-certificates \
    git

RUN git clone https://github.com/teslamotors/vehicle-command.git . \
    && git checkout "${VEHICLE_COMMAND_REF}" \
    && go mod download \
    && mkdir -p /out \
    && CGO_ENABLED=0 go build -o /out ./...

FROM $BUILD_FROM

RUN apk add --no-cache \
    bash \
    curl \
    gettext \
    jq \
    libstdc++ \
    libsodium \
    nginx \
    nginx-mod-stream \
    openssl \
    py3-pip \
    python3 \
    zeromq \
    && pip3 install --no-cache-dir --break-system-packages \
        "authlib==1.7.2" \
        "requests==2.34.2"

COPY --from=fleet_telemetry_build /go/bin/fleet-telemetry /usr/local/bin/fleet-telemetry
COPY --from=vehicle_command_build /out/tesla-http-proxy /usr/local/bin/tesla-http-proxy
COPY --from=vehicle_command_build /out/tesla-auth-token /usr/local/bin/tesla-auth-token
COPY --from=vehicle_command_build /out/tesla-control /usr/local/bin/tesla-control
COPY --from=vehicle_command_build /out/tesla-keygen /usr/local/bin/tesla-keygen

COPY rootfs/ /

RUN chmod 0755 /usr/local/bin/*.sh /usr/local/bin/*.py /etc/services.d/tesla_fleet_gateway/run \
    && rm -f /etc/nginx/nginx.conf.template
