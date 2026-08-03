FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# 배포 파이프라인은 infra/docker/frontend.Dockerfile 을 쓴다. 이 파일은 로컬에서
# 컨테이너를 직접 띄워볼 때용이므로, 빌드 인자를 그쪽과 같게 맞춰 둔다 —
# 없으면 API 주소가 빈 채로 구워져 화면이 아무것도 못 불러온다.
ARG VITE_API_BASE_URL=""
ARG VITE_USE_MOCKS="false"
ARG VITE_DEFAULT_MAP_ID=""
ARG VITE_DEFAULT_ROBOT_ID=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_USE_MOCKS=${VITE_USE_MOCKS} \
    VITE_DEFAULT_MAP_ID=${VITE_DEFAULT_MAP_ID} \
    VITE_DEFAULT_ROBOT_ID=${VITE_DEFAULT_ROBOT_ID}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
