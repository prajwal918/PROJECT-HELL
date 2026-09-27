FROM node:20-alpine

# Metadata
LABEL maintainer="project-hell"
LABEL version="2.0.0"
LABEL description="PROJECT-HELL - Hardened Enterprise Node.js Backend Service"
LABEL security.hardened="true"

WORKDIR /app

# Copy package manifests
COPY package*.json ./

# Install production dependencies deterministically
RUN npm install --omit=dev --ignore-scripts && \
    chown -R node:node /app

# Copy application source code with non-root ownership
COPY --chown=node:node . .

# Switch to unprivileged system user
USER node

EXPOSE 80

# Automated HTTP healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:' + (process.env.PORT || 80) + '/', (r) => { process.exit(r.statusCode === 200 ? 0 : 1); })" || exit 1

CMD ["npm", "start"]