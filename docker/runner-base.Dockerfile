# Scopelet Generic Multi-Language Isolated Runner
FROM alpine:3.20

# Install minimal runtimes and security tools
RUN apk add --no-cache \
    nodejs \
    npm \
    python3 \
    git \
    bash \
    coreutils

# Create sandbox user and group
RUN addgroup -S sandbox && adduser -S -G sandbox -s /bin/bash sandbox

WORKDIR /sandbox
RUN chown -R sandbox:sandbox /sandbox

USER sandbox

ENTRYPOINT ["/bin/bash", "-c"]
