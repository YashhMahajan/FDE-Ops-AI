# The static web UI with the flagship demo data. Three stages: demo data, site, server.
FROM python:3.12-slim AS demo
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY tenants ./tenants
COPY configs ./configs
COPY incidents ./incidents
RUN uv sync --locked --no-dev \
 && uv run fdeops demo --tenant tenants/ledgerloop --out /tmp/demo --export /demo \
 && uv run fdeops demo --tenant tenants/parcelpoint --out /tmp/demo --export /demo

FROM node:22-slim AS site
RUN corepack enable && corepack prepare pnpm@11 --activate
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web ./
COPY --from=demo /demo ./public/demo
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=site /web/out /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
