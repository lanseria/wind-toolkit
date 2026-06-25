# Atmos Toolkit

GFS 多气象变量数据获取与地图可视化工具。从 NOAA GFS（Global Forecast System）0.25° 预报数据集下载 **16 种气象变量**（风场 U/V、温度、湿度、云量、能见度、降水、气压、阵风、位势高度等），生成暗色主题的精美气象地图 PNG，并切割为透明 XYZ 瓦片供 Web 地图叠加使用。

## 数据集

| 属性 | 值 |
|------|------|
| 数据源 | NOAA GFS (Global Forecast System) |
| 分辨率 | 0.25° × 0.25°（约 25 km） |
| 等压面层 | 1000 / 850 / 700 / 500 / 300 / 250 / 200 / 100 hPa |
| 变量数 | 16 种气象变量 |
| 预报周期 | 每 6 小时发布（00/06/12/18 UTC） |
| 预报时长 | 默认 24 小时，可配置 |
| 数据延迟 | 发布后约 4 小时可获取 |
| 下载方式 | NOMADS GRIB Filter API（按变量+区域子集下载） |
| 覆盖区域 | 全球（90°N–90°S, 180°W–180°E） |
| 许可 | NOAA 公开数据，无需 API 密钥 |

### 可用变量清单

通过 `--variable/-v` 指定变量名，所有变量通过 `config.VARIABLES` 字典配置驱动：

| 变量 key | 含义 | 层级 | 单位 | colormap |
|---------|------|------|------|---------|
| `wind` | 风场 U/V 分量（矢量，含风向箭头+粒子数据） | 等压面 8 层 | m/s | wind_speed |
| `temp` | 温度 | 等压面 8 层 + 2m | °C | temp |
| `rh` | 相对湿度 | 等压面 8 层 + 2m | % | humidity |
| `spfh` | 比湿 | 等压面 8 层 + 2m | g/kg | humidity |
| `dpt` | 露点温度 | 2m | °C | temp |
| `hgt` | 位势高度 | 等压面 8 层 | m | geo_height |
| `tcdc` | 总云量 | 整层大气 | % | cloud |
| `lcdc` | 低云量 | 整层大气 | % | cloud |
| `mcdc` | 中云量 | 整层大气 | % | cloud |
| `hcdc` | 高云量 | 整层大气 | % | cloud |
| `vis` | 能见度 | 地表 | km | visibility |
| `apcp` | 累计降水 | 地表 | mm | precip |
| `prate` | 降水率 | 地表 | mm/h | precip |
| `pres` | 地表气压 | 地表 | hPa | pressure |
| `prmsl` | 海平面气压 | 海平面 | hPa | pressure |
| `gust` | 地表阵风 | 地表 | m/s | wind_speed |

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
NOAA GFS 0.25° 气象变量 → GRIB Filter 子集下载 → NetCDF
    → 气象地图 PNG（暗色主题完整地图，按变量+层级分目录）
    → 透明 XYZ 瓦片（按变量+层级分目录，可叠加任意底图）
```

1. **数据获取**：通过 NOMADS GRIB Filter API 下载指定变量的 GFS 子集（自动按变量配置选择 `lev_xxx` 层级参数），自动回溯检测最新可用预报周期
2. **地图生成**：加载 NetCDF → 单位转换 → 高斯平滑（sigma=1.5）+ 4× 三次插值增强 → cartopy 暗色主题地图渲染 PNG
3. **瓦片生成**：从原始数据直接生成透明 RGBA 叠加层 → PlateCarree 重投影为 Web Mercator XYZ 瓦片（zoom 3–4，256×256）
4. **瓦片清单**：每个 (variable, level) 组合生成 `tiles_manifest.json`（`lastUpdated` + Unix 时间戳数组），客户端可轮询获取可用时刻

## 输出说明

### 气象地图 PNG（`outputs/textures/{variable}/{level_token}/`）

完整暗色主题气象地图，包含：

- **数据色斑**：按变量自适应 colormap，contourf 等值线填充（温度/湿度/云量/降水/能见度等）
- **风向箭头**（仅风场）：白色 quiver 箭头，稀疏采样
- **地理要素**：cartopy 海岸线、中国国界 shapefile、九段线
- **辅助元素**：colorbar（按变量单位）、经纬度网格线、UTC/BJT 双时区标题、层级标注

### 透明 XYZ 瓦片（`atmos-tiles/{variable}/{level_token}/`）

仅包含数据色斑（风场含风向箭头）的透明 RGBA 瓦片，无底图、无标签、无地图要素，可直接叠加在任意 Web 地图底图上（Leaflet/Mapbox 等）。

- 数据色斑 alpha = 0.8（风场）或 0.85（标量），无数据区域全透明
- 风向箭头白色 alpha = 0.5（仅风场）
- Web Mercator 投影（EPSG:3857），zoom 3–4，256×256
- 每个瓦片文件名按时间戳区分：`{z}/{x}/{y}/{unix_timestamp}.png`
- 每个变量+层级独立目录：`atmos-tiles/wind/850hPa/`、`atmos-tiles/temp/2m/`、`atmos-tiles/tcdc/atmos/` 等

瓦片清单 `tiles_manifest.json` 格式（每个 variable+level 独立一份）：

```json
{
  "lastUpdated": "2026-06-24T16:27:54+08:00",
  "timestamps": [1782259200, 1782262800, 1782266400]
}
```

风场变量额外包含 `particle` 字段：

```json
{
  "lastUpdated": "...",
  "timestamps": [...],
  "particle": {
    "available": true,
    "filenames": ["1782259200.json", "1782262800.json"]
  }
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
cd atmos-toolkit

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
| `SCHEDULE_VARIABLES` | 调度模式下处理的变量列表（逗号分隔），如 `wind,temp,tcdc` | `wind` |
| `NUM_WORKERS` | 并行工作进程数 | CPU 核数 / 2 |
| `TILES_HOST_PATH` | 瓦片输出到宿主机的路径（Docker 部署用） | `./atmos-tiles` |
| `MAP_DATA_ROOT` | 地图数据根目录（Docker 部署时设为 `/app`） | `../chromasky-toolkit` |

## 使用

```bash
# 默认流程（风场所有等压面层：下载 + 生成地图 + 生成瓦片）
python -m src.atmos_toolkit.main

# 仅处理风场 850 hPa 层
python -m src.atmos_toolkit.main --level 850

# 处理温度 850 hPa 层
python -m src.atmos_toolkit.main -v temp --level 850

# 处理温度所有层级（8 等压面 + 2m）
python -m src.atmos_toolkit.main -v temp

# 处理多个变量
python -m src.atmos_toolkit.main --variables wind temp tcdc vis

# 处理所有 16 个变量所有适用层级
python -m src.atmos_toolkit.main --all-variables

# 仅下载数据
python -m src.atmos_toolkit.main --acquire-only

# 仅生成地图和瓦片（使用已有数据）
python -m src.atmos_toolkit.main --process-only

# 按 GFS 周期智能调度（00/06/12/18 UTC + 延迟后自动运行）
python -m src.atmos_toolkit.main --schedule

# 获取 48 小时预报
python -m src.atmos_toolkit.main --forecast-hours 48
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

# 处理温度变量
docker compose run --rm app -v temp --level 850
```

> Docker 镜像构建时会自动下载地图 shapefile 和字体数据，无需额外配置。瓦片目录通过 `TILES_HOST_PATH` 映射到宿主机，方便 Web 服务直接访问。

## 输出结构

```
data/
  raw/                                  # GFS GRIB2 子集
    wind/1000hPa/, wind/850hPa/, ...    # 等压面风场
    temp/850hPa/, temp/2m/, ...         # 温度（等压面 + 2m）
    tcdc/atmos/                         # 总云量（整层大气）
    vis/surface/                        # 能见度（地表）
    prmsl/msl/                          # 海平面气压
  processed/                            # 合并裁切后的 NetCDF
    wind/850hPa/wind_merged.nc
    temp/2m/temp_merged.nc
    tcdc/atmos/tcdc_merged.nc
outputs/
  textures/                             # 气象地图 PNG
    wind/850hPa/{unix_ts}.png
    temp/2m/{unix_ts}.png
    tcdc/atmos/{unix_ts}.png
atmos-tiles/
  wind/850hPa/                          # 风场瓦片（含粒子数据）
    tiles_manifest.json
    particle/{unix_ts}.json
    {z}/{x}/{y}/{unix_ts}.png
  temp/2m/                              # 温度 2m 瓦片（无粒子）
    tiles_manifest.json
    {z}/{x}/{y}/{unix_ts}.png
  tcdc/atmos/                           # 总云量瓦片
    tiles_manifest.json
    {z}/{x}/{y}/{unix_ts}.png
```

## 项目结构

```
src/atmos_toolkit/
  config.py              # 全局配置：变量字典 VARIABLES、COLORMAPS、等压面层、路径函数
  data_acquisition.py    # NOMADS GRIB Filter 下载、自动周期检测、合并裁切
  processor.py           # NetCDF 加载、变量名识别、逐帧地图/瓦片生成调度
  map_visualizer.py      # 暗色主题气象地图渲染：字体、colormap、cartopy 绘图
  tile_generator.py      # 透明 XYZ 瓦片生成（标量+风场双轨）+ 瓦片清单 manifest
  cleanup.py             # 过期数据清理（支持 variable+level 二维）
  wind_data_generator.py # 风场粒子流 JSON 数据生成（仅风场）
  main.py                # CLI 入口：--variable/-v 多变量、--schedule 智能调度
  utils.py               # 通用工具：logger、时区转换、时间戳格式化
```

## License

MIT
