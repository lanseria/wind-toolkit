# Wind Toolkit

GFS 多层等压面风场数据获取与地图可视化工具。从 NOAA GFS（Global Forecast System）0.25° 预报数据集下载 **8 个等压面**（1000–100 hPa）的 U/V 风场分量（UGRD/VGRD），生成暗色主题的精美风场地图 PNG，并切割为透明 XYZ 瓦片供 Web 地图叠加使用。

## 数据集

| 属性 | 值 |
|------|------|
| 数据源 | NOAA GFS (Global Forecast System) |
| 分辨率 | 0.25° × 0.25°（约 25 km） |
| 等压面层 | **1000 / 850 / 700 / 500 / 300 / 250 / 200 / 100 hPa** |
| 变量 | UGRD（U-component of wind）、VGRD（V-component of wind） |
| 预报周期 | 每 6 小时发布（00/06/12/18 UTC） |
| 预报时长 | 默认 24 小时，可配置 |
| 数据延迟 | 发布后约 4 小时可获取 |
| 下载方式 | NOMADS GRIB Filter API（按变量+区域子集下载） |
| 覆盖区域 | 全球（90°N–90°S, 180°W–180°E） |
| 许可 | NOAA 公开数据，无需 API 密钥 |

### 等压面层与对应高度

| 等压面 | 大约高度 |
|--------|---------|
| 1000 hPa | ~100 m |
| 850 hPa | ~1,500 m |
| 700 hPa | ~3,000 m |
| 500 hPa | ~5,500 m |
| 300 hPa | ~9,000 m |
| 250 hPa | ~10,000 m |
| 200 hPa | ~12,000 m |
| 100 hPa | ~16,000 m |

## 工作流程

```
NOAA GFS 0.25° 8 层等压面 Wind → GRIB Filter 子集下载 → NetCDF (UGRD/VGRD)
    → 风场地图 PNG（暗色主题完整地图，按层分目录）
    → 透明 XYZ 瓦片（按层分目录，仅风速色斑 + 风向箭头，可叠加任意底图）
```

1. **数据获取**：通过 NOMADS GRIB Filter API 下载 GFS 8 个等压面风场子集（仅请求 UGRD/VGRD 变量 + 对应等压面 + 指定区域），自动回溯检测最新可用预报周期
2. **地图生成**：加载 NetCDF → 高斯平滑（sigma=1.5）+ 4× 三次插值增强 → cartopy 暗色主题地图渲染 PNG
3. **瓦片生成**：从原始风场数据直接生成透明 RGBA 叠加层 → PlateCarree 重投影为 Web Mercator XYZ 瓦片（zoom 3–8，256×256）
4. **瓦片清单**：每层生成 `tiles_manifest.json`（`lastUpdated` + Unix 时间戳数组），客户端可轮询获取可用时刻

## 输出说明

### 风场地图 PNG（`outputs/textures/{level}/`）

完整暗色主题风场地图，包含：

- **风速色斑**：自定义深蓝→青→绿→黄→橙→红 colormap，contourf 等值线填充
- **风向箭头**：白色 quiver 箭头，稀疏采样
- **地理要素**：cartopy 海岸线、中国国界 shapefile、九段线
- **辅助元素**：colorbar（m/s）、经纬度网格线、UTC/BJT 双时区标题、高度层标注

### 透明 XYZ 瓦片（`wind-tiles/{level}/`）

仅包含风速色斑 + 风向箭头的透明 RGBA 瓦片，无底图、无标签、无地图要素，可直接叠加在任意 Web 地图底图上（Leaflet/Mapbox 等）。

- 风速色斑 alpha = 0.8，无数据区域全透明
- 风向箭头白色 alpha = 0.5
- Web Mercator 投影（EPSG:3857），zoom 3–8，256×256
- 每个瓦片文件名按时间戳区分：`{z}/{x}/{y}/{unix_timestamp}.png`
- 每层独立目录：`wind-tiles/850hPa/`、`wind-tiles/500hPa/` 等

瓦片清单 `tiles_manifest.json` 格式（每层独立一份）：

```json
{
  "lastUpdated": "2026-05-19T15:31:38+08:00",
  "timestamps": [1779062400, 1779066000, 1779069600]
}
```

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- **无需 API 密钥**（GFS 数据为 NOAA 公开数据）

> **Windows 用户注意**：`cfgrib` 依赖 `eccodes` C 库。如果安装失败，请先通过 conda 安装：
> ```bash
> conda install -c conda-forge eccodes
> ```

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd wind-toolkit

# 安装依赖
uv sync
# 或
pip install -e .
```

## 配置

复制 `.env.example` 为 `.env` 并按需修改（所有配置均有默认值，可不配置直接运行）：

```bash
cp .env.example .env
```

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `GFS_FORECAST_HOURS` | GFS 预报时长（小时） | `24` |
| `GFS_LATENCY_HOURS` | GFS 数据发布延迟（小时） | `4` |
| `NUM_WORKERS` | 并行工作进程数 | CPU 核数 / 2 |
| `TILES_HOST_PATH` | 瓦片输出到宿主机的路径（Docker 部署用） | `./wind-tiles` |
| `MAP_DATA_ROOT` | 地图数据根目录（Docker 部署时设为 `/app`） | `../chromasky-toolkit` |

## 使用

```bash
# 完整流程（所有层：下载 + 生成地图 + 生成瓦片）
python -m src.wind_toolkit.main

# 仅处理 850 hPa 层
python -m src.wind_toolkit.main --level 850

# 仅下载数据
python -m src.wind_toolkit.main --acquire-only

# 仅生成地图和瓦片（使用已有数据）
python -m src.wind_toolkit.main --process-only

# 按 GFS 周期智能调度（00/06/12/18 UTC + 延迟后自动运行）
python -m src.wind_toolkit.main --schedule

# 获取 48 小时预报
python -m src.wind_toolkit.main --forecast-hours 48
```

## Docker 部署

```bash
# 构建镜像
docker compose build

# 后台运行（按 GFS 周期智能调度）
docker compose up -d

# 查看日志
docker compose logs -f

# 一次性运行（获取 48 小时预报）
docker compose run --rm app --forecast-hours 48

# 仅生成地图（使用已有数据）
docker compose run --rm app --process-only

# 仅处理单层
docker compose run --rm app --level 500 --forecast-hours 6
```

> Docker 镜像构建时会自动下载地图 shapefile 和字体数据，无需额外配置。瓦片目录通过 `TILES_HOST_PATH` 映射到宿主机，方便 Web 服务直接访问。

## 输出结构

```
data/
  raw/                        # GFS GRIB2 子集（按等压面层分目录）
    1000hPa/
    850hPa/
    ...
  processed/                  # 合并裁切后的 NetCDF（按等压面层分目录）
    1000hPa/wind_merged.nc
    850hPa/wind_merged.nc
    ...
outputs/
  textures/                   # 风场地图 PNG（按等压面层分目录）
    1000hPa/YYYYMMDD_HHMM.png
    850hPa/YYYYMMDD_HHMM.png
    ...
wind-tiles/
  1000hPa/                    # 透明 XYZ 瓦片 + 清单
    tiles_manifest.json
    {z}/{x}/{y}/1779062400.png
  850hPa/
    tiles_manifest.json
    {z}/{x}/{y}/1779062400.png
  ...
```

## 项目结构

```
src/wind_toolkit/
  config.py              # 全局配置：地理范围、等压面层定义、GFS 参数、路径
  data_acquisition.py    # NOMADS GRIB Filter 下载、自动周期检测、合并裁切
  processor.py           # NetCDF 加载、变量名识别、逐帧地图/瓦片生成调度
  map_visualizer.py      # 暗色主题风场地图渲染：字体、colormap、cartopy 绘图
  tile_generator.py      # 透明 XYZ 瓦片生成 + 瓦片清单 manifest
  main.py                # CLI 入口：完整流水线 / GFS 周期智能调度 / 单层执行
  utils.py               # 通用工具：logger、时区转换、时间戳格式化
```

## License

MIT
