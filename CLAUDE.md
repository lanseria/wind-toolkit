# CLAUDE.md

## Project Overview

Wind Toolkit 是一个 Python GFS 多层等压面风场数据获取与地图可视化工具。它从 NOAA GFS（Global Forecast System）0.25° 预报数据集下载 8 个等压面（1000/850/700/500/300/250/200/100 hPa）的 U/V 风场分量，生成暗色主题的精美风场地图 PNG（风速色斑 + 风向箭头 + 海岸线国界 + colorbar），并切割为 XYZ 瓦片供 Web 地图使用。Python 3.12+，使用 uv 管理依赖。

## Commands

```bash
# 安装依赖
pip install -e .

# 命令行工作流
python -m src.wind_toolkit.main                       # 完整流程（所有层）
python -m src.wind_toolkit.main --level 850            # 仅处理 850 hPa
python -m src.wind_toolkit.main --acquire-only        # 仅下载数据
python -m src.wind_toolkit.main --process-only        # 仅生成地图（使用已有数据）
python -m src.wind_toolkit.main --schedule            # 按 GFS 周期智能调度
python -m src.wind_toolkit.main --forecast-hours 48   # 获取 48 小时预报

# Docker 部署
docker compose build                                  # 构建镜像
docker compose up -d                                  # 后台运行（按 GFS 周期智能调度）
docker compose logs -f                                # 查看日志
docker compose run --rm app --process-only            # 一次性运行（仅生成地图）
docker compose run --rm app --level 500 --forecast-hours 6  # 仅处理单层
```

## Architecture

### 数据流水线（多等压面层）

1. **数据获取** (`data_acquisition.py`): 循环 8 个等压面层，通过 NOMADS GRIB Filter 下载 GFS 0.25° 的 U/V 风场分量，自动检测最新可用预报周期，每个预报时刻下载一个 GRIB2 子集，合并裁切到展示区域后保存为 `data/processed/{level}/wind_merged.nc`
2. **地图生成** (`processor.py` + `map_visualizer.py`): 加载 NetCDF → 逐帧调用 `generate_wind_map()` 生成暗色主题风场地图 PNG（标题含高度层信息），输出到 `outputs/textures/{level}/`
3. **瓦片生成** (`tile_generator.py`): 将 PlateCarree 投影的风场地图切割为 Web Mercator XYZ 瓦片，缩放级别 3-8，输出到 `wind-tiles/{level}/{z}/{x}/{y}/{unix_timestamp}.png`
4. **瓦片清单** (`tile_generator.py`): 每层生成 `wind-tiles/{level}/tiles_manifest.json`，包含所有可用时间戳

### 等压面层定义

`config.py` 中 `PRESSURE_LEVELS` 定义了 8 个等压面层（1000/850/700/500/300/250/200/100 hPa），每层包含 `hpa`、`label`、`height`、`grib_param`。`--level` CLI 参数可指定单个 hPa 值只处理该层。

### 地图可视化要素

- **底图**: cartopy PlateCarree 投影，深色背景（海洋 #0c0a09，陆地 #1c1917）
- **风速色斑**: contourf 填充等值线，自定义深蓝→青→绿→黄→橙→红 colormap，高斯平滑 + 4x 三次插值
- **风向箭头**: quiver 叠加，半透明白色箭头
- **地理要素**: 海岸线、中国国界 shapefile、九段线
- **辅助元素**: colorbar（风速 m/s）、经纬度网格线、UTC/BJT 双时区标题 + 高度层标注

### 核心模块

| 模块 | 职责 |
|------|------|
| `config.py` | 中央配置：等压面层定义、地理范围、GFS 参数、按层动态路径函数 |
| `data_acquisition.py` | NOMADS GRIB Filter 下载（按层参数化）、自动周期检测、合并裁切 |
| `processor.py` | NetCDF 加载、变量名识别、逐帧调用地图生成与瓦片切割（按层参数化） |
| `map_visualizer.py` | 暗色主题风场地图渲染：字体、colormap、cartopy 绘图、高度层标题 |
| `tile_generator.py` | XYZ 瓦片生成：PlateCarree→Web Mercator 重投影切割 + 按层瓦片清单 manifest |
| `main.py` | CLI 入口：多等压面层循环处理 / 单层 `--level` / GFS 周期智能调度 |
| `utils.py` | 通用工具：logger、时区转换、时间戳格式化 |

### 关键设计

- **数据源**: NOAA GFS 0.25° 预报数据，通过 NOMADS GRIB Filter API 按变量+区域+等压面子集下载，无需 API 密钥
- **多层等压面**: 8 个等压面层独立下载、处理、输出，目录按 `{hpa}hPa` 分隔
- **动态路径**: `config.py` 提供 `tile_dir_for_level()` / `textures_dir_for_level()` 等函数，按 hPa 值动态生成路径
- **地理范围二级结构**: `DISPLAY_AREA`（展示范围，默认全球）→ `DOWNLOAD_AREA`（下载缓冲，扩展 `BUFFER_DEGREES` 度，全球时自动 clamp 到地球边界）
- **经度归一化**: GFS 数据经度可能为 0–360，`merge_and_crop()` 中自动归一化到 -180–180 以匹配展示区域
- **自动周期检测**: 自动回溯查找最新可用 GFS 预报周期（通常延迟约 4 小时）
- **智能调度**: `--schedule` 模式按 GFS 周期（00/06/12/18 UTC + 延迟）自动运行，非固定间隔轮询
- **单层执行**: `--level 850` 仅处理指定等压面层，加速调试和按需使用
- **瓦片清单**: 每层独立 `tiles_manifest.json`（`lastUpdated` + `timestamps` 数组），客户端可轮询获取可用时间戳
- **视觉增强**: 高斯平滑(sigma=1.5) + 4x 三次插值，使风速色斑过渡平滑
- **字体系统**: 优先加载 chromasky-toolkit 共享的 LXGW WenKai 字体，回退到系统中文字体
- **XYZ 瓦片**: 从原始风场数据直接生成透明 RGBA 瓦片（仅风速色斑+风向箭头，无底图/标签），通过 `_build_overlay()` 生成 PlateCarree 叠加层再切割为 Web Mercator 瓦片

### 路径约定

- 源码在 `src/wind_toolkit/`
- `config.py` 中 `PROJECT_ROOT` = `src/` 目录，所有数据路径使用 `PROJECT_ROOT.parent / "xxx"`
- 按等压面层分隔的路径：`data/raw/{hpa}hPa/`、`data/processed/{hpa}hPa/`、`outputs/textures/{hpa}hPa/`、`wind-tiles/{hpa}hPa/`
- 地图资源（shapefile、字体）默认引用 `../chromasky-toolkit/` 共享资源，Docker 部署时通过 `MAP_DATA_ROOT` 环境变量覆盖
- Docker 镜像构建时通过 `tools/setup_map_data.py` 下载地图数据和字体到容器内
- 无需 `.env` 即可运行（所有配置有默认值），但可通过 `.env` 覆盖

## Code Style

- 使用中文注释
- 日志使用 `logging` 模块，logger 命名按模块区分
- 类型注解使用 Python 3.12+ 语法（`str | None` 而非 `Optional[str]`）
