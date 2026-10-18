# Scopelet Isolated Runner - Node 22 Base Image
# Hardened container for hermetic test execution and delta-debugging.

FROM node:22-alpine

# Set non-interactive and timezone
ENV NODE_ENV=test
ENV TZ=UTC

# Create non-root user directory
WORKDIR /app

# Ensure proper permissions for non-root node user
RUN chown -R node:node /app

# Switch to non-root user for security
USER node

# Default entrypoint for test execution
ENTRYPOINT ["npm", "test"]
