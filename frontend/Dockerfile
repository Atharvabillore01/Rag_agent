FROM node:20-alpine
WORKDIR /app

# Install deps first (cached layer — only re-runs when package.json changes)
COPY package.json package-lock.json* ./
RUN npm install

# Copy source (overridden by volume mount in dev)
COPY . .

EXPOSE 3000

# --host 0.0.0.0 is required so the dev server is reachable outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
