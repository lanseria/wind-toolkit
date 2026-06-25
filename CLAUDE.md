# CLAUDE.md

## Project Overview

Atmos Toolkit 是一个 Python GFS 多气象变量数据获取与地图可视化工具。它从 NOAA GFS（Global Forecast System）0.25° 预报数据集下载 16 种气象变量（风场 U/V、温度、湿度、云量、能见度、降水、气压、阵风、位势高度等），生成暗色主题的气象地图 PNG（数据色斑 + 海岸线国界 + colorbar；风场含风向箭头），并切割为透明 XYZ 瓦片供 Web 地图叠加使用。Python 3.12+，使用 uv 管理依赖。

## Commands

```bash
# 安装依赖
pip install -e .

# 命令行工作流
python -m src.atmos_toolkit.main                       # 默认风场所有层
python -m src.atmos_toolkit.main -v temp --level 850    # 温度 850 hPa
python -m src.atmos_toolkit.main -v temp                # 温度所有层级（8 等压面 + 2m）
python -m src.atmos_toolkit.main --variables wind tcdc vis  # 多变量批量
python -m src.atmos_toolkit.main --all-variables        # 全部 16 个变量
python -m src.atmos_toolkit.main --acquire-only        # 仅下载数据
python -m src.atmos_toolkit.main --process-only        # 仅生成地图（使用已有数据）
python -m src.atmos_toolkit.main --schedule            # 按 GFS 周期智能调度
python -m src.atmos_toolkit.main --forecast-hours 48   # 获取 48 小时预报

# Docker 部署
docker compose build                                  # 构建镜像
docker compose up -d                                  # 后台运行（按 GFS 周期智能调度）
docker compose logs -f                                # 查看日志
docker compose run --rm app --process-only            # 一次性运行（仅生成地图）
docker compose run --rm app -v temp --level 500       # 仅处理单变量单层
```

## Architecture

### 数据流水线（多气象变量）

1. **数据获取** (`data_acquisition.py`): 按 `(variable, level)` 组合通过 NOMADS GRIB Filter 下载 GFS 0.25° 数据，自动检测最新可用预报周期，每个预报时刻下载一个 GRIB2 子集，合并裁切到展示区域后保存为 `data/processed/{variable}/{level_token}/{variable}_merged.nc`
2. **地图生成** (`processor.py` + `map_visualizer.py`): 加载 NetCDF → 单位转换 → 逐帧调用 `generate_scalar_map()` / `generate_wind_map()` 生成暗色主题气象地图 PNG，输出到 `outputs/textures/{variable}/{level_token}/`
3. **瓦片生成** (`tile_generator.py`): 将数据色斑生成透明 RGBA 叠加层后，PlateCarree 重投影切割为 Web Mercator XYZ 瓦片，缩放级别 3-4，输出到 `atmos-tiles/{variable}/{level_token}/{z}/{x}/{y}/{unix_timestamp}.png`
4. **瓦片清单** (`tile_generator.py`): 每个 (variable, level_token) 组合生成 `atmos-tiles/{variable}/{level_token}/tiles_manifest.json`

### 变量配置驱动

`config.py` 中 `VARIABLES` 字典定义了 16 个变量，每项包含：`display_name`、`grib_vars`、`kind`（vector/scalar）、`nc_names`（NetCDF 候选名）、`unit`/`unit_display`/`convert`、`level_type`（isobaric/single/both）、`single_level_key`、`cmap`、`vmin_vmax`、`title_template`、可选 `step_type`（cfgrib stepType 冲突时使用）。

新增变量只需在 `VARIABLES` 字典中加一项，主流程（下载/合并/渲染/瓦片）无需改动。

### 层级类型与 token 映射

- `isobaric`: 等压面层（wind/temp 等压面/rh 等压面/spfh 等压面/hgt），按 8 个 PRESSURE_LEVELS 处理
- `single`: 单层（vis/tcdc/pres/prmsl/gust/dpt），按 `single_level_key` 映射到 GRIB 层级参数和目录 token
- `both`: 既支持等压面也支持 2m（temp/rh/spfh），`--level` 缺省时同时生成 8 等压面 + 2m

`LEVEL_KEY_MAP` 映射 single_level_key 到 NOMADS 的 `lev_xxx`（注意 GFS 0p25 中 2m 是 `lev_2_m_above_ground`，数字与单位间有下划线）。`SINGLE_LEVEL_KEYS` 映射到目录 token（surface/2m/10m/atmos/msl）。

### 地图可视化要素

- **底图**: cartopy PlateCarree 投影，深色背景（海洋 #0c0a09，陆地 #1c1917）
- **数据色斑**: contourf 填充等值线，按变量自适应 colormap（7 种共享色阶），高斯平滑 + 4x 三次插值
- **风向箭头**: quiver 叠加，半透明白色箭头（仅风场）
- **地理要素**: 海岸线、中国国界 shapefile、九段线
- **辅助元素**: colorbar（按变量单位）、经纬度网格线、UTC/BJT 双时区标题 + 层级标注

### 核心模块

| 模块 | 职责 |
|------|------|
| `config.py` | 中央配置：VARIABLES 字典、COLORMAPS、UNIT_CONVERTERS、PRESSURE_LEVELS、按 (variable, level) 寻址的路径函数 |
| `data_acquisition.py` | NOMADS GRIB Filter 下载（任意 var_names 列表 + lev_xxx）、自动周期检测、合并裁切 |
| `processor.py` | NetCDF 加载、变量名识别、vector/scalar 分支处理（含单位转换）、逐帧调度 |
| `map_visualizer.py` | 暗色主题气象地图渲染：抽取 7 个通用辅助函数 + generate_scalar_map + generate_wind_map |
| `tile_generator.py` | 透明 XYZ 瓦片生成（标量+风场双轨）+ 瓦片清单 manifest |
| `cleanup.py` | 过期数据清理（支持 variable+level 二维） |
| `wind_data_generator.py` | 风场粒子流 JSON 数据生成（仅 wind 变量） |
| `main.py` | CLI 入口：`--variable/-v` 多变量、`--variables`、`--all-variables`、`--schedule` 智能调度 |
| `utils.py` | 通用工具：logger、时区转换、时间戳格式化 |

### 关键设计

- **数据源**: NOAA GFS 0.25° 预报数据，通过 NOMADS GRIB Filter API 按变量+层级+区域子集下载，无需 API 密钥
- **配置驱动**: 所有变量元信息集中在 `config.VARIABLES` 字典，主流程对任意变量通用，新增变量零代码改动
- **双轨渲染**: 风场保留 `generate_wind_map/tiles`（含粒子+箭头），标量变量走 `generate_scalar_map/tiles`，共享底图/海岸线/网格/标题/colorbar 辅助函数
- **粒度独立**: 每个 `(variable, level)` 组合独立下载、独立目录、独立 manifest
- **路径二级寻址**: `tile_dir_for(var_name, hpa, single_level_key)` 等通用函数按 `(variable, level_token)` 寻址，旧 `tile_dir_for_level(hpa)` 等保留为 wind 别名
- **地理范围二级结构**: `DISPLAY_AREA`（展示范围，默认全球）→ `DOWNLOAD_AREA`（下载缓冲，扩展 `BUFFER_DEGREES` 度，全球时自动 clamp 到地球边界）
- **经度归一化**: GFS 数据经度可能为 0–360，`merge_and_crop()` 中自动归一化到 -180–180 以匹配展示区域
- **周期检测与变量解耦**: `_find_latest_cycle()` 始终用 UGRD + lev_850_mb 探测，与具体下载的变量无关
- **cfgrib stepType 自适应**: `_open_grib_dataset()` 默认不带 filter，遇到 stepType 冲突自动回退到 `filter_by_keys={'stepType': ...}`（如 APCP/PRATE 用 avg）
- **单位转换**: `UNIT_CONVERTERS` 表 + `apply_unit_convert(data, var_cfg)` 集中管理（K→°C、Pa→hPa、m→km、kg/kg→g/kg、PRATE→mm/h）
- **7 种共享色阶**: 16 变量共享 wind_speed/temp/humidity/cloud/precip/visibility/pressure/geo_height，避免视觉杂乱
- **自动周期检测**: 自动回溯查找最新可用 GFS 预报周期（通常延迟约 4 小时）
- **智能调度**: `--schedule` 模式按 GFS 周期（00/06/12/18 UTC + 延迟）自动运行，通过 `SCHEDULE_VARIABLES` 环境变量配置多变量调度（默认 wind）
- **瓦片清单**: 每个 (variable, level) 独立 `tiles_manifest.json`（`lastUpdated` + `timestamps` 数组），风场额外含 `particle` 字段
- **视觉增强**: 高斯平滑(sigma=1.5) + 4x 三次插值，使数据色斑过渡平滑
- **字体系统**: 优先加载 chromasky-toolkit 共享的 LXGW WenKai 字体，回退到系统中文字体
- **透明 RGBA 瓦片**: 从原始数据直接生成透明瓦片（仅数据色斑，风场含箭头，无底图/标签），通过 `_build_scalar_overlay()` / `_build_wind_overlay()` 生成 PlateCarree 叠加层再切割为 Web Mercator 瓦片

### 路径约定

- 源码在 `src/atmos_toolkit/`
- `config.py` 中 `PROJECT_ROOT` = `src/` 目录，所有数据路径使用 `PROJECT_ROOT.parent / "xxx"`
- 按 **变量 + 层级 token** 分隔的路径：`data/raw/{variable}/{level_token}/`、`data/processed/{variable}/{level_token}/`、`outputs/textures/{variable}/{level_token}/`、`atmos-tiles/{variable}/{level_token}/`
- level_token 规则：等压面变量为 `{hpa}hPa`（如 `850hPa`），单层变量为虚拟 token（`surface`/`2m`/`atmos`/`msl`）
- 地图资源（shapefile、字体）默认引用 `../chromasky-toolkit/` 共享资源，Docker 部署时通过 `MAP_DATA_ROOT` 环境变量覆盖
- Docker 镜像构建时通过 `tools/setup_map_data.py` 下载地图数据和字体到容器内
- 无需 `.env` 即可运行（所有配置有默认值），但可通过 `.env` 覆盖

### ⚠️ 破坏性变更

- **atmos-tiles 目录结构变更**: 从 `atmos-tiles/{hpa}hPa/` 改为 `atmos-tiles/wind/{hpa}hPa/`，所有变量统一为 `atmos-tiles/{variable}/{level_token}/`。前端 URL 模板需同步更新。

## Code Style

- 使用中文注释
- 日志使用 `logging` 模块，logger 命名按模块区分
- 类型注解使用 Python 3.12+ 语法（`str | None` 而非 `Optional[str]`）
