FROM node:20-slim

WORKDIR /app

# 依存関係のインストール（キャッシュ効率化のため先に package.json のみをコピー）
COPY node-app/package*.json ./node-app/
RUN cd node-app && npm install --omit=dev

# ソースコードと静的ファイルのコピー
COPY node-app ./node-app
COPY public_html ./public_html

WORKDIR /app/node-app

EXPOSE 3000

CMD ["node", "index.js"]
