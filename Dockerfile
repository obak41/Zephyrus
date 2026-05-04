# 軽量なPython 3.11イメージを使用
FROM python:3.11-slim

# タイムゾーンをJSTに設定（ログ出力などを日本時間に合わせるため）
ENV TZ=Asia/Tokyo

# 作業ディレクトリを作成
WORKDIR /app

# 依存関係のインストールに必要な最小限のツールを導入（必要に応じて）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt をコピーしてパッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# プロジェクトの全ファイルをコピー
COPY . .

# Botを実行
CMD ["python", "main.py"]