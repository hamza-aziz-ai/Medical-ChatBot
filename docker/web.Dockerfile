# syntax=docker/dockerfile:1
# Web image: the built Vue frontend served by unprivileged nginx, which proxies /api/ to the API.
# Build from the repository root: docker build -f docker/web.Dockerfile .
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS build
WORKDIR /app
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --non-interactive
COPY frontend/ ./
# Same-origin API path; never pass the API token as a build argument.
ARG VITE_API_BASE_URL=/api
RUN yarn build

FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
