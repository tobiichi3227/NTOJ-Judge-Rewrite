FROM python:3.14-slim AS development
SHELL ["/bin/bash", "-c"]

RUN apt update \
    && pip install tornado aiofiles --break-system-packages

WORKDIR /ntoj-judge-demo
COPY ./ .

EXPOSE 8080
CMD /ntoj/scripts/runserver.sh
