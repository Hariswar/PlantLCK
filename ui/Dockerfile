FROM node:jod-alpine
WORKDIR ./app
COPY package.json .
COPY package-lock.json .
RUN npm install
COPY . .
# RUN npm run build
