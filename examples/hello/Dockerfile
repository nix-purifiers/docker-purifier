FROM quay.io/prometheus/busybox:latest AS build
COPY message.txt /message.txt
RUN cat /message.txt > /proof.txt
FROM quay.io/prometheus/busybox:latest
COPY --from=build /proof.txt /proof.txt
CMD ["cat", "/proof.txt"]
