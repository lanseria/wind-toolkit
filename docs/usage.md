# Atmos Toolkit 前端使用指南

Atmos Toolkit 输出 16 种气象变量的可叠加 Web 地图数据：

- **XYZ 瓦片**（透明 RGBA PNG）：数据色斑（风场含风向箭头），以 `raster` 图层叠加
- **粒子 JSON**（wind-layer jsonArray 格式，仅风场）：用于动态风力粒子流动效果

两种数据可独立使用，也可叠加形成色斑底 + 流动粒子的组合效果。

---

## 目录结构

瓦片与粒子数据按 **变量 + 层级** 分目录存储，文件名均为 Unix 时间戳（秒）：

```
atmos-tiles/
  wind/                                  ← 风场（含粒子）
    850hPa/
      tiles_manifest.json                ← 该变量+层级可用时间戳清单
      particle/                          ← 粒子风场 JSON（仅 wind 变量）
        1779062400.json
        1779066000.json
      3/{x}/{y}/1779062400.png           ← 透明 RGBA 瓦片
    500hPa/
      ...
  temp/                                  ← 温度（无粒子）
    850hPa/
      tiles_manifest.json
      3/{x}/{y}/{unix_ts}.png
    2m/
      ...
  tcdc/                                  ← 总云量（无粒子）
    atmos/
      tiles_manifest.json
      3/{x}/{y}/{unix_ts}.png
```

### 可用变量与层级 token

| 变量 key | 含义 | 层级 token | 单位 | 含粒子 |
|---------|------|-----------|------|--------|
| `wind` | 风场（U/V 分量 + 风向箭头） | `1000hPa`/`850hPa`/.../`100hPa` | m/s | ✓ |
| `temp` | 温度 | 等压面 8 层 + `2m` | °C | |
| `rh` | 相对湿度 | 等压面 8 层 + `2m` | % | |
| `spfh` | 比湿 | 等压面 8 层 + `2m` | g/kg | |
| `dpt` | 露点温度 | `2m` | °C | |
| `hgt` | 位势高度 | 等压面 8 层 | m | |
| `tcdc` | 总云量 | `atmos` | % | |
| `lcdc` | 低云量 | `atmos` | % | |
| `mcdc` | 中云量 | `atmos` | % | |
| `hcdc` | 高云量 | `atmos` | % | |
| `vis` | 能见度 | `surface` | km | |
| `apcp` | 累计降水 | `surface` | mm | |
| `prate` | 降水率 | `surface` | mm/h | |
| `pres` | 地表气压 | `surface` | hPa | |
| `prmsl` | 海平面气压 | `msl` | hPa | |
| `gust` | 地表阵风 | `surface` | m/s | |

### 瓦片规格

- **投影**: Web Mercator (EPSG:3857)
- **缩放级别**: 3 – 4
- **瓦片尺寸**: 256 × 256
- **格式**: PNG with RGBA（透明背景）
- **XYZ URL**: `{base}/{variable}/{level_token}/{z}/{x}/{y}/{timestamp}.png`

---

## tiles_manifest.json

每个 (variable, level_token) 根目录下的清单文件，记录所有可用时间戳：

```json
{
  "lastUpdated": "2026-06-24T16:27:54+08:00",
  "timestamps": [1779062400, 1779066000, 1779069600]
}
```

风场变量（`wind`）额外包含 `particle` 字段：

```json
{
  "lastUpdated": "2026-06-24T16:27:54+08:00",
  "timestamps": [1779062400, 1779066000, 1779069600],
  "particle": {
    "available": true,
    "filenames": ["1779062400.json", "1779066000.json", "1779069600.json"]
  }
}
```

- `timestamps`: Unix 时间戳数组（秒），**直接就是瓦片文件名**
- `particle.filenames`: 粒子 JSON 文件名数组（仅 `wind` 变量）
- 拼接瓦片 URL：`${variable}/${level_token}/{z}/{x}/${y}/${timestamps[i]}.png`

---

## XYZ 瓦片叠加

### 粒子 JSON 格式（仅风场）

每个 JSON 文件是两元素数组，分别包含 U（东西方向）和 V（南北方向）风场分量：

```json
[
  {
    "header": {
      "parameterCategory": 2,
      "parameterNumber": 2,
      "dx": 0.25,
      "dy": 0.25,
      "la1": 54.0,
      "la2": 0.0,
      "lo1": 70.0,
      "lo2": 135.0,
      "nx": 261,
      "ny": 217,
      "refTime": "2026-05-18T00:00:00Z"
    },
    "data": [0.5312, -1.2344, null, 2.1094, ...]
  },
  {
    "header": {
      "parameterCategory": 2,
      "parameterNumber": 3,
      ...
    },
    "data": [0.125, 0.875, null, -0.5, ...]
  }
]
```

| 字段 | 说明 |
|------|------|
| `parameterNumber` | 2 = U 分量，3 = V 分量 |
| `dx` / `dy` | 经纬度分辨率（度） |
| `la1` / `la2` | 起始/结束纬度（北→南扫描） |
| `lo1` / `lo2` | 起始/结束经度 |
| `nx` / `ny` | 经度/纬度方向网格点数 |
| `refTime` | 参考时间（ISO 8601 UTC） |
| `data` | 扁平数组（ny × nx），按行扫描（北→南，西→东），`null` = 无数据 |

---

## MapLibre GL JS

### 静态瓦片叠加（单个时刻）

```js
const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'],
        tileSize: 256,
      },
      wind: {
        type: 'raster',
        tiles: ['https://your-tiles-server.com/atmos-tiles/wind/850hPa/{z}/{x}/{y}/1779062400.png'],
        tileSize: 256,
        minzoom: 3,
        maxzoom: 8,
      }
    },
    layers: [
      { id: 'basemap', type: 'raster', source: 'basemap' },
      { id: 'wind-layer', type: 'raster', source: 'wind', paint: { 'raster-opacity': 0.85 } }
    ]
  },
  center: [105, 30],
  zoom: 4
});
```

### 多变量叠加（风场 + 温度 + 云量）

```js
const ts = 1779062400;
const layers = [
  { id: 'wind',  path: 'wind/850hPa',     opacity: 0.7 },
  { id: 'temp',  path: 'temp/2m',         opacity: 0.6 },
  { id: 'tcdc',  path: 'tcdc/atmos',      opacity: 0.7 },
];

layers.forEach(({ id, path, opacity }) => {
  map.addSource(id, {
    type: 'raster',
    tiles: [`https://your-tiles-server.com/atmos-tiles/${path}/{z}/{x}/${y}/${ts}.png`],
    tileSize: 256, minzoom: 3, maxzoom: 8
  });
  map.addLayer({
    id: `${id}-layer`, type: 'raster', source: id,
    paint: { 'raster-opacity': opacity }
  });
});
```

### 动态切换时间（时间轴播放）

```js
const VAR = 'wind';
const LEVEL_TOKEN = '850hPa';
const TILE_BASE = 'https://your-tiles-server.com/atmos-tiles';

let timestamps = [];
let currentIndex = 0;

async function loadManifest() {
  const res = await fetch(`${TILE_BASE}/${VAR}/${LEVEL_TOKEN}/tiles_manifest.json`);
  timestamps = (await res.json()).timestamps;
}

function showFrame(index) {
  const ts = timestamps[index];
  const url = `${TILE_BASE}/${VAR}/${LEVEL_TOKEN}/{z}/{x}/{y}/${ts}.png`;
  if (map.getSource('wind')) {
    map.removeLayer('wind-layer');
    map.removeSource('wind');
  }
  map.addSource('wind', { type: 'raster', tiles: [url], tileSize: 256, minzoom: 3, maxzoom: 8 });
  map.addLayer({ id: 'wind-layer', type: 'raster', source: 'wind', paint: { 'raster-opacity': 0.85 } });
  document.getElementById('time-label').textContent = new Date(ts * 1000).toUTCString();
}

loadManifest().then(() => {
  showFrame(0);
  setInterval(() => {
    currentIndex = (currentIndex + 1) % timestamps.length;
    showFrame(currentIndex);
  }, 1000);
});
```

### 多层叠加（多个等压面同时显示）

```js
const levels = ['850hPa', '500hPa', '250hPa'];
const ts = 1779062400;

levels.forEach(hpa => {
  map.addSource(`wind-${hpa}`, {
    type: 'raster',
    tiles: [`https://your-tiles-server.com/atmos-tiles/wind/${hpa}/{z}/{x}/${y}/${ts}.png`],
    tileSize: 256, minzoom: 3, maxzoom: 8
  });
  map.addLayer({
    id: `wind-${hpa}-layer`, type: 'raster', source: `wind-${hpa}`,
    paint: { 'raster-opacity': 0.7 }
  });
});
```

---

## Mapbox GL JS

Mapbox 用法几乎相同，区别仅在于初始化方式：

```js
mapboxgl.accessToken = 'YOUR_MAPBOX_TOKEN';

const map = new mapboxgl.Map({
  container: 'map',
  style: 'mapbox://styles/mapbox/dark-v11',
  center: [105, 30],
  zoom: 4
});

map.on('load', () => {
  map.addSource('wind', {
    type: 'raster',
    tiles: ['https://your-tiles-server.com/atmos-tiles/wind/850hPa/{z}/{x}/{y}/1779062400.png'],
    tileSize: 256, minzoom: 3, maxzoom: 8
  });
  map.addLayer({ id: 'wind-layer', type: 'raster', source: 'wind', paint: { 'raster-opacity': 0.85 } });
});
```

---

## 风力粒子流（wind-layer）

粒子效果使用 `@sakitam-gis/wind-layer` 库，与 Atmos Toolkit 生成的粒子 JSON 完全兼容。**仅 `wind` 变量有粒子数据**。

```bash
npm install @sakitam-gis/wind-layer
```

### 推荐颜色配置

与风速色斑瓦片保持一致：

```js
const colorScale = [
  '#043b6e',  // 深蓝 - 微风
  '#0096c7',  // 蓝
  '#48cae4',  // 青蓝
  '#90e0ef',  // 浅青
  '#caffbf',  // 浅绿
  '#fdffb6',  // 浅黄
  '#ffd166',  // 黄
  '#f4845f',  // 橙
  '#d62828',  // 红
  '#9d0208',  // 深红 - 强风
];
```

### 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `velocityScale` | 1/25 | 速度缩放，值越大约子移动越快 |
| `particleCount` | 8000 | 粒子数量，越多越密集（影响性能） |
| `maxAge` / `particleAge` | 90 | 粒子最大存活帧数，越大拖尾越长 |
| `lineWidth` | 2 | 粒子线宽（像素） |
| `fadeOpacity` | 0.96 | 拖尾淡出系数，越大拖尾越明显 |
| `colorScale` | 见上 | 按风速映射的颜色数组 |

### 按缩放级别调优

```js
map.on('zoom', () => {
  const zoom = map.getZoom();
  const count = zoom > 5 ? 12000 : zoom > 3 ? 8000 : 5000;
  if (windLayer) windLayer.updateParams({ particleCount: count });
});
```

---

## 瓦片 + 粒子叠加

先添加色斑瓦片，再叠加粒子层，形成组合效果（仅风场）：

```js
// 色斑瓦片（底图上层）
map.addSource('wind-raster', {
  type: 'raster',
  tiles: [`${TILE_BASE}/wind/${LEVEL}/{z}/{x}/${y}/${ts}.png`],
  tileSize: 256, minzoom: 3, maxzoom: 8
});
map.addLayer({
  id: 'wind-raster-layer', type: 'raster', source: 'wind-raster',
  paint: { 'raster-opacity': 0.5 }
});

// 粒子层
const res = await fetch(`${TILE_BASE}/wind/${LEVEL}/particle/${ts}.json`);
const data = await res.json();
const windLayer = new WindLayer.WindLayer('wind-particles', data, {
  windOptions: {
    velocityScale: 1 / 25,
    maxAge: 90, lineWidth: 2, particleCount: 8000,
    colorScale: ['#043b6e', '#0096c7', '#48cae4', '#90e0ef', '#caffbf',
                 '#fdffb6', '#ffd166', '#f4845f', '#d62828', '#9d0208'],
    fadeOpacity: 0.96,
  },
  map: map,
});
```

---

## 完整示例

### MapLibre GL JS（瓦片 + 粒子 + 时间轴）

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Atmos Toolkit - 风场地图</title>
  <link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet" />
  <script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
  <script src="https://unpkg.com/@sakitam-gis/wind-layer@1/dist/wind-layer.js"></script>
  <style>
    body { margin: 0; }
    #map { position: absolute; top: 0; bottom: 0; width: 100%; }
    #controls {
      position: absolute; top: 10px; left: 10px; z-index: 1;
      background: rgba(0,0,0,0.75); color: #fff; padding: 12px 16px;
      border-radius: 8px; font-family: sans-serif; font-size: 14px;
    }
    #controls select, #controls button { margin: 4px; cursor: pointer; }
    #time-label { margin: 0 8px; }
  </style>
</head>
<body>
  <div id="controls">
    <div>
      <label>等压面层:
        <select id="level-select">
          <option value="1000hPa">1000 hPa (~100 m)</option>
          <option value="850hPa" selected>850 hPa (~1,500 m)</option>
          <option value="700hPa">700 hPa (~3,000 m)</option>
          <option value="500hPa">500 hPa (~5,500 m)</option>
          <option value="300hPa">300 hPa (~9,000 m)</option>
          <option value="250hPa">250 hPa (~10,000 m)</option>
          <option value="200hPa">200 hPa (~12,000 m)</option>
          <option value="100hPa">100 hPa (~16,000 m)</option>
        </select>
      </label>
    </div>
    <div>
      <button id="prev">&#9664;</button>
      <span id="time-label">--</span>
      <button id="next">&#9654;</button>
      <button id="play-btn">播放</button>
    </div>
  </div>
  <div id="map"></div>

  <script>
    const TILE_BASE = 'https://your-tiles-server.com/atmos-tiles';
    let timestamps = [];
    let idx = 0;
    let timer = null;
    let currentLevel = '850hPa';
    let windLayer = null;

    const map = new maplibregl.Map({
      container: 'map',
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster',
            tiles: ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'],
            tileSize: 256,
          }
        },
        layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }]
      },
      center: [105, 30],
      zoom: 4
    });

    async function loadManifest() {
      const res = await fetch(`${TILE_BASE}/wind/${currentLevel}/tiles_manifest.json`);
      const data = await res.json();
      timestamps = data.timestamps;
      idx = timestamps.length - 1;
    }

    async function showFrame() {
      const ts = timestamps[idx];

      // 更新瓦片图层
      const url = `${TILE_BASE}/wind/${currentLevel}/{z}/{x}/{y}/${ts}.png`;
      if (map.getSource('wind')) { map.removeLayer('wind-layer'); map.removeSource('wind'); }
      map.addSource('wind', { type: 'raster', tiles: [url], tileSize: 256, minzoom: 3, maxzoom: 8 });
      map.addLayer({ id: 'wind-layer', type: 'raster', source: 'wind', paint: { 'raster-opacity': 0.5 } });

      // 更新粒子层
      if (windLayer) { windLayer.remove(); windLayer = null; }
      const particleRes = await fetch(`${TILE_BASE}/wind/${currentLevel}/particle/${ts}.json`);
      const particleData = await particleRes.json();
      windLayer = new WindLayer.WindLayer('wind-particles', particleData, {
        windOptions: {
          velocityScale: 1 / 25, maxAge: 90, lineWidth: 2, particleCount: 8000,
          colorScale: ['#043b6e','#0096c7','#48cae4','#90e0ef','#caffbf','#fdffb6','#ffd166','#f4845f','#d62828','#9d0208'],
          fadeOpacity: 0.96,
        },
        map: map,
      });

      document.getElementById('time-label').textContent =
        new Date(ts * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
    }

    map.on('load', async () => {
      await loadManifest();
      await showFrame();

      document.getElementById('prev').onclick = () => { idx = (idx - 1 + timestamps.length) % timestamps.length; showFrame(); };
      document.getElementById('next').onclick = () => { idx = (idx + 1) % timestamps.length; showFrame(); };
      document.getElementById('play-btn').onclick = (e) => {
        if (timer) { clearInterval(timer); timer = null; e.target.textContent = '播放'; }
        else { timer = setInterval(() => { idx = (idx + 1) % timestamps.length; showFrame(); }, 3000); e.target.textContent = '暂停'; }
      };
      document.getElementById('level-select').onchange = async (e) => {
        currentLevel = e.target.value;
        await loadManifest();
        await showFrame();
      };
    });
  </script>
</body>
</html>
```

### Mapbox GL JS（瓦片 + 粒子 + 时间轴）

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Atmos Toolkit - 风场地图</title>
  <link href="https://unpkg.com/mapbox-gl@3/dist/mapbox-gl.css" rel="stylesheet" />
  <script src="https://unpkg.com/mapbox-gl@3/dist/mapbox-gl.js"></script>
  <script src="https://unpkg.com/@sakitam-gis/wind-layer@1/dist/wind-layer.js"></script>
  <style>
    body { margin: 0; }
    #map { position: absolute; top: 0; bottom: 0; width: 100%; }
    #controls {
      position: absolute; top: 10px; left: 10px; z-index: 1;
      background: rgba(0,0,0,0.75); color: #fff; padding: 12px 16px;
      border-radius: 8px; font-family: sans-serif; font-size: 14px;
    }
    #controls button { margin: 0 4px; cursor: pointer; }
    #time-label { margin: 0 8px; }
  </style>
</head>
<body>
  <div id="controls">
    <button id="prev">&#9664;</button>
    <span id="time-label">--</span>
    <button id="next">&#9654;</button>
    <button id="play-btn">播放</button>
  </div>
  <div id="map"></div>

  <script>
    mapboxgl.accessToken = 'YOUR_MAPBOX_TOKEN';
    const TILE_BASE = 'https://your-tiles-server.com/atmos-tiles';
    const LEVEL = '850hPa';
    let timestamps = [];
    let idx = 0;
    let timer = null;
    let windLayer = null;

    const map = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [105, 30],
      zoom: 4
    });

    async function loadManifest() {
      const res = await fetch(`${TILE_BASE}/wind/${LEVEL}/tiles_manifest.json`);
      timestamps = (await res.json()).timestamps;
      idx = timestamps.length - 1;
    }

    async function showFrame() {
      const ts = timestamps[idx];

      // 瓦片图层
      const url = `${TILE_BASE}/wind/${LEVEL}/{z}/{x}/{y}/${ts}.png`;
      if (map.getSource('wind')) { map.removeLayer('wind-layer'); map.removeSource('wind'); }
      map.addSource('wind', { type: 'raster', tiles: [url], tileSize: 256, minzoom: 3, maxzoom: 8 });
      map.addLayer({ id: 'wind-layer', type: 'raster', source: 'wind', paint: { 'raster-opacity': 0.5 } });

      // 粒子层
      if (windLayer) { windLayer.remove(); windLayer = null; }
      const data = await (await fetch(`${TILE_BASE}/wind/${LEVEL}/particle/${ts}.json`)).json();
      windLayer = new WindLayer.WindLayer('wind-particles', data, {
        windOptions: {
          velocityScale: 1 / 25, maxAge: 90, lineWidth: 2, particleCount: 8000,
          colorScale: ['#043b6e','#0096c7','#48cae4','#90e0ef','#caffbf','#fdffb6','#ffd166','#f4845f','#d62828','#9d0208'],
          fadeOpacity: 0.96,
        },
        map: map,
      });

      document.getElementById('time-label').textContent =
        new Date(ts * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
    }

    map.on('load', async () => {
      await loadManifest();
      await showFrame();
      document.getElementById('prev').onclick = () => { idx = (idx - 1 + timestamps.length) % timestamps.length; showFrame(); };
      document.getElementById('next').onclick = () => { idx = (idx + 1) % timestamps.length; showFrame(); };
      document.getElementById('play-btn').onclick = (e) => {
        if (timer) { clearInterval(timer); timer = null; e.target.textContent = '播放'; }
        else { timer = setInterval(() => { idx = (idx + 1) % timestamps.length; showFrame(); }, 3000); e.target.textContent = '暂停'; }
      };
    });
  </script>
</body>
</html>
```

将 `TILE_BASE` 和 `accessToken` 替换为实际值即可使用。

---

## 自定义 WebGL 实现

如果不使用 wind-layer 库，可基于 WebGL 自行实现粒子渲染：

1. 解析 JSON 获取 U/V 数据数组和网格元信息
2. 将 U/V 数组上传为两个 WebGL 纹理（`LUMINANCE` 格式，将 `null` 替换为 0）
3. 使用粒子更新着色器：根据当前位置采样 U/V 纹理，计算下一帧位置
4. 使用渲染着色器：绘制带拖尾的粒子线段

参考实现：
- [mapbox/webgl-wind](https://github.com/mapbox/webgl-wind) — Mapbox 官方博客的 WebGL 风场方案
- [Esri/wind-js](https://github.com/Esri/wind-js) — 经典 Canvas 2D 实现

---

## 部署瓦片服务

瓦片和粒子 JSON 都是静态文件，用任意静态文件服务即可提供。

### nginx

```nginx
server {
    listen 80;
    server_name tiles.example.com;

    location /atmos-tiles/ {
        alias /path/to/atmos-tiles/;
        add_header Access-Control-Allow-Origin *;
        add_header Cache-Control "public, max-age=3600";

        # JSON 自动 gzip
        gzip on;
        gzip_types application/json;
        gzip_min_length 256;
    }
}
```

风场瓦片 URL：`http://tiles.example.com/atmos-tiles/wind/850hPa/{z}/{x}/{y}/1779062400.png`
温度瓦片 URL：`http://tiles.example.com/atmos-tiles/temp/2m/{z}/{x}/{y}/1779062400.png`
云量瓦片 URL：`http://tiles.example.com/atmos-tiles/tcdc/atmos/{z}/{x}/{y}/1779062400.png`
粒子 URL（仅风场）：`http://tiles.example.com/atmos-tiles/wind/850hPa/particle/1779062400.json`

### Python 一行启动（开发测试）

```bash
cd atmos-toolkit
python -m http.server 8080
```

瓦片 URL：`http://localhost:8080/atmos-tiles/wind/850hPa/{z}/{x}/{y}/1779062400.png`
