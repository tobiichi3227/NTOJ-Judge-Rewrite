FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY src/sandbox .
# RUN apk add --no-cache git && GOPRIVATE=github.com/tobiichi3227/go-sandbox go mod tidy && go build -ldflags="-s -w" -o sandbox .
RUN apk add --no-cache git && GOPRIVATE=github.com/tobiichi3227/go-sandbox go mod tidy && go build -ldflags="-s -w" -o sandbox .
# RUN go build -ldflags="-s -w" -o sandbox .
# RUN go build -gcflags "-N -l" -o sandbox .

FROM ubuntu:24.04 AS release

RUN apt update \
    && apt install -y make gcc g++ clang llvm python3 python3-pip rustc openjdk-17-jdk --no-install-suggests --no-install-recommends \
    && apt clean \
    && pip install cffi tornado --break-system-packages

WORKDIR /judge
COPY src .

WORKDIR /judge/sandbox
COPY --from=builder /src/sandbox .
WORKDIR /judge/default-checker
RUN make

WORKDIR /judge
CMD ["python3", "/judge/server.py"]
