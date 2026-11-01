# The mobile app's WEB version: built once into static files and served by nginx. Used by docker-compose.app.yml.
# (For the iOS simulator or a phone with Expo Go, run `make mobile` instead; that needs Node.js on your machine.)
FROM node:22-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# These values are baked into the bundle at build time. The browser (on your computer) calls the backend through the
# published port, so the address is localhost. Demo mode must be exactly "true" in a release build (see src/demo.ts).
ARG EXPO_PUBLIC_API_URL=http://localhost:8000
ARG EXPO_PUBLIC_DEMO_MODE=true
ENV EXPO_PUBLIC_API_URL=$EXPO_PUBLIC_API_URL EXPO_PUBLIC_DEMO_MODE=$EXPO_PUBLIC_DEMO_MODE CI=1 EXPO_NO_TELEMETRY=1
RUN npx expo export --platform web

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
