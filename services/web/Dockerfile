FROM node:22-slim AS base

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

# Development: Vite dev server with hot reload. Used only by the local
# docker-compose.override.yml — never by a deployed environment.
FROM base AS dev
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# Build the static production bundle. No API URL is baked in; the app
# calls the same-origin /api path, which nginx proxies to the api service.
FROM base AS build
RUN npm run build

# Production runtime: nginx serves the static bundle and reverse-proxies
# /api to the api service. This is the image every deployed environment runs.
FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
