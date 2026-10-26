# Web (02 §3): Next.js standalone server. Build context is apps/web.
FROM node:24-slim AS deps
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-slim AS build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
# The browser opens the live socket itself, so this is the host-visible API address, inlined at build.
ARG NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/live
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
COPY --from=deps /web/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-slim AS run
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /web/.next/standalone ./
COPY --from=build --chown=node:node /web/.next/static ./.next/static
COPY --from=build --chown=node:node /web/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
