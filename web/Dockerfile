# Multi-stage build for the Arbiter cockpit (Next.js 15, standalone output).
# docs/28 §3 item 9 — the `web` image.
#
# pnpm comes from the `packageManager` field in package.json via corepack. We
# refresh corepack first so it knows the pinned pnpm release, and disable the
# download prompt so the build is non-interactive.

FROM node:20-slim AS deps
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN npm install -g corepack@latest && corepack enable
WORKDIR /app
COPY web/package.json web/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    corepack prepare --activate && pnpm install --frozen-lockfile

FROM node:20-slim AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1
RUN npm install -g corepack@latest && corepack enable
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY web/ ./
RUN corepack prepare --activate && pnpm build

FROM node:20-slim AS runtime
WORKDIR /app
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin nextjs
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nextjs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nextjs /app/public ./public
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
    CMD node -e "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"
CMD ["node", "server.js"]
