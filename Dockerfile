FROM m.daocloud.io/ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# --- 1. 配置 APT 清华镜像源 ---
RUN echo "\
Types: deb\n\
URIs: https://mirrors.tuna.tsinghua.edu.cn/debian/\n\
Suites: bookworm bookworm-updates bookworm-backports\n\
Components: main contrib non-free non-free-firmware\n\
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\
" > /etc/apt/sources.list.d/debian.sources

# --- 2. 安装系统依赖 ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgeos-dev \
    tzdata \
    build-essential \
    libeccodes-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 3. 环境变量 ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app \
    PYTHONPATH=/app/src \
    MPLCONFIGDIR=/app/config/matplotlib \
    CARTOPY_DATA_DIR=/app/data/cartopy_data \
    MAP_DATA_ROOT=/app \
    UV_TOOL_BIN_DIR=/usr/local/bin

# --- 4. 安装 Python 依赖（利用 BuildKit 缓存） ---
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /app
RUN mkdir -p /app/config/matplotlib /app/data/cartopy_data /app/map_data /app/fonts /app/outputs
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# --- 5. 预下载 Cartopy 自然地球数据 ---
RUN --mount=type=cache,target=/app/data/cartopy_data \
    python -c "import cartopy.io.shapereader as shpreader; \
    shpreader.natural_earth(resolution='50m', category='physical', name='land'); \
    shpreader.natural_earth(resolution='50m', category='physical', name='ocean'); \
    shpreader.natural_earth(resolution='50m', category='physical', name='coastline');"

# --- 6. 下载地图数据和字体 ---
RUN python tools/setup_map_data.py

# --- 7. 持久化目录 ---
VOLUME /app/data
VOLUME /app/outputs

# --- 8. 入口 ---
ENTRYPOINT ["python", "-m", "src.wind_toolkit.main"]
CMD ["--schedule"]
