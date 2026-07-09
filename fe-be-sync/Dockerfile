# fe-be-sync/Dockerfile
# Stage 1: build Vite/React app
FROM node:22-alpine AS builder

WORKDIR /app

# Install deps first (layer cache)
COPY fe-be-sync/package.json fe-be-sync/package-lock.json fe-be-sync/

RUN cd fe-be-sync && npm ci

# Copy all source files
COPY fe-be-sync fe-be-sync/

# Build static assets
RUN cd fe-be-sync && npm run build

# Stage 2: serve with nginx
FROM nginx:1.27-alpine

COPY --from=builder /app/fe-be-sync/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
