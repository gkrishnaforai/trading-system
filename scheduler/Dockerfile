FROM alpine:3.20

RUN apk add --no-cache curl ca-certificates bash

WORKDIR /app

COPY scheduler/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV GO_API_URL=http://go-api:8000
ENV SCHEDULER_TICK_INTERVAL_SECONDS=30

CMD ["/app/entrypoint.sh"]
