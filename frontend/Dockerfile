FROM node:20-alpine

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

COPY frontend /app/frontend

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG API_BASE_URL_SERVER=http://backend:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV API_BASE_URL_SERVER=${API_BASE_URL_SERVER}

RUN npm run build

EXPOSE 3000

CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port 3000"]
