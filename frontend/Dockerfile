# syntax=docker/dockerfile:1
# Build the Vite SPA, then serve the static bundle with nginx.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_* are baked into the bundle at build time (pass via --build-arg)
ARG VITE_API_URL
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_MAPS_API_KEY
ENV VITE_API_URL=$VITE_API_URL \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_MAPS_API_KEY=$VITE_MAPS_API_KEY
RUN npm run build

FROM nginx:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:80/ >/dev/null 2>&1 || exit 1
