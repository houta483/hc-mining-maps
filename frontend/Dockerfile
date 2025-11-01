# Multi-stage build for React frontend
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json ./

# Install dependencies (use npm ci for production builds)
RUN npm install

# Copy source files
COPY . .

# Build argument for Mapbox token
ARG MAPBOX_TOKEN
ENV MAPBOX_TOKEN=${MAPBOX_TOKEN}

# Build the app
RUN npm run build

# Production stage: Serve static files with nginx
FROM nginx:alpine

# Copy built files to nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace default server config with SPA-friendly config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create script to inject Mapbox token into index.html at runtime
RUN echo '#!/bin/sh' > /docker-entrypoint.sh && \
  echo 'if [ -n "$MAPBOX_TOKEN" ]; then' >> /docker-entrypoint.sh && \
  echo '  sed -i "s|window.MAPBOX_TOKEN = \"\"|window.MAPBOX_TOKEN = \"$MAPBOX_TOKEN\"|g" /usr/share/nginx/html/index.html' >> /docker-entrypoint.sh && \
  echo 'fi' >> /docker-entrypoint.sh && \
  echo 'exec nginx -g "daemon off;"' >> /docker-entrypoint.sh && \
  chmod +x /docker-entrypoint.sh

EXPOSE 80

CMD ["/docker-entrypoint.sh"]

