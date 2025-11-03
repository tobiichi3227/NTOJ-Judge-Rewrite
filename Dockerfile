FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY src/sandbox .
RUN apk add --no-cache git && GOPRIVATE=github.com/tobiichi3227/go-sandbox go mod tidy && go build -ldflags="-s -w" -o sandbox .

FROM debian:13-slim AS release

RUN apt update \
    && apt install -y make gcc g++ clang llvm python3 python3-pip rustc openjdk-21-jdk-headless --no-install-suggests --no-install-recommends \
    && apt clean \
    && pip install cffi tornado --break-system-packages \
    && rm -rf /var/lib/apt/lists/

WORKDIR /judge
COPY src .

WORKDIR /judge/sandbox
COPY --from=builder /src/sandbox .
WORKDIR /judge/default-checker
RUN make

WORKDIR /judge
EXPOSE 2502
CMD ["python3", "/judge/server.py"]
