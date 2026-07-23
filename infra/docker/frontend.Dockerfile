FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG VITE_API_BASE_URL=""
ARG VITE_USE_MOCKS="false"
ARG VITE_DEFAULT_MAP_ID="1"
ARG VITE_DEFAULT_ROBOT_ID="1"
ARG VITE_STATS_ENDPOINT="/api/statistics"
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_USE_MOCKS=${VITE_USE_MOCKS} \
    VITE_DEFAULT_MAP_ID=${VITE_DEFAULT_MAP_ID} \
    VITE_DEFAULT_ROBOT_ID=${VITE_DEFAULT_ROBOT_ID} \
    VITE_STATS_ENDPOINT=${VITE_STATS_ENDPOINT}

RUN test "${VITE_USE_MOCKS}" = "false" && npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
