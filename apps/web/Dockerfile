FROM node:24.19.0-bookworm-slim

WORKDIR /app
RUN npm install --global pnpm@11.19.0
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./

ENV VITE_API_PROXY_TARGET=http://api:8000
EXPOSE 5173
CMD ["pnpm", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
