# 板材直切排样 API

面向小型加工坊的矩形零件直切（guillotine）排样服务。输入母板尺寸、锯缝宽度、
母板数量上限与零件清单（含数量、可旋转标记），输出**仅由贯穿当前余料区域的
直切**组成的可执行方案：每块零件的母板编号、坐标、朝向、按顺序排列的切割线，
以及余料矩形。

- 技术栈：Python 3.11+ · FastAPI · SQLite（标准库 `sqlite3`，零外部服务）
- 排样引擎为纯 Python（`app/nesting.py`），无任何第三方依赖
- 保证：零件不重叠、不越界、零件间留有锯缝占位；相同输入必得相同布局；
  放不下的零件在响应中明确列出并附原因

## 快速开始（一条命令）

```bash
docker compose up --build
```

依赖安装与数据库初始化全部包含在该命令内（应用启动时自动建表，幂等）。

- 服务地址：http://localhost:8000
- 交互式文档（Swagger UI）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- SQLite 数据文件：容器内 `/data/plans.db`（由命名卷 `nesting-data` 持久化）

### 本地开发（不用 Docker）

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000   # 启动时自动初始化 ./data/plans.db
pytest                                       # 运行测试
```

数据库路径可用环境变量 `DB_PATH` 覆盖（默认 `./data/plans.db`）。

## API

### 生成方案 `POST /api/v1/plans`

```bash
curl -X POST http://localhost:8000/api/v1/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "sheet": {"width": 2440, "height": 1220, "kerf": 3, "max_sheets": 5},
    "parts": [
      {"id": "door",  "width": 800,  "height": 400, "quantity": 4, "rotatable": true},
      {"id": "shelf", "width": 600,  "height": 300, "quantity": 6},
      {"id": "side",  "width": 1200, "height": 250, "quantity": 2, "rotatable": true}
    ]
  }'
```

请求字段：

| 字段 | 说明 |
| --- | --- |
| `sheet.width` / `sheet.height` | 母板宽 / 高（>0） |
| `sheet.kerf` | 锯缝宽度（≥0，默认 3） |
| `sheet.max_sheets` | 母板数量上限（≥1，默认 100） |
| `parts[].id` | 零件标识，请求内唯一 |
| `parts[].width` / `parts[].height` | 零件尺寸（>0） |
| `parts[].quantity` | 数量（≥1，默认 1） |
| `parts[].rotatable` | 是否允许旋转 90°（默认 false） |

响应（201）要点：

- `status`：`complete` 全部排入 / `partial` 部分排入 / `failed` 全部未排入
- `summary`：母板用量、零件计数、切割刀数、利用率 `utilization`
- `sheets[].placements[]`：`part_id`、`instance`、`label`（如 `door#2`）、
  `x`、`y`、`width`、`height`、`rotated`（朝向）
- `sheets[].cuts[]`：按执行顺序编号（`seq`）的切割线，
  `orientation` 为 `H`（水平）/`V`（垂直），端点 `(x1,y1)-(x2,y2)` 与 `length`
- `sheets[].leftovers[]`：余料矩形 `x`、`y`、`width`、`height`、`area`
- `unplaced[]`：未排零件清单，`reason` 为
  `exceeds_sheet_size`（单件超过母板尺寸）或
  `no_remaining_space`（母板数量上限内无足够空间）

### 查询方案

```bash
curl http://localhost:8000/api/v1/plans            # 列表（摘要，倒序，支持 limit/offset）
curl http://localhost:8000/api/v1/plans/<plan_id>  # 完整方案；不存在返回 404
```

## 切割语义（重要）

- **坐标系**：原点在母板左下角，x 向右，y 向上；单位与输入一致（通常毫米）。
- **锯缝**：每一刀在切割线的余料侧消耗 `kerf` 宽度材料，零件始终得到名义尺寸；
  相邻零件之间因此至少间隔一个锯缝。不足一个锯缝的边条记为废料（仍会产生
  一刀修边切割线）。
- **执行顺序**：每块母板的 `cuts` 按 `seq` 升序执行。每一刀都完整贯穿
  "当前被切的那一片材料"（从一边到另一边），即标准直切/闸刀式切割；
  按序执行即可逐片复现整个排样，不存在需要先叠合再切的刀。
- **余料**：`leftovers` 是全部切割完成后剩余的可用矩形（未做相邻合并，
  保持直切结构）。

## 结果稳定性

排样引擎不使用任何随机数：零件按固定全序规则排序，放置采用评分键全序的
best-fit，分裂方向按固定规则选择。因此**相同输入永远得到相同布局**
（`plan_id`、`created_at` 除外）。测试 `test_determinism` 与
`test_same_input_stable_layout` 对此做了验证。

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

覆盖：不越界、零件两两间隔 ≥ 锯缝、切割序列可执行性仿真（逐刀模拟锯切，
最终物理片必须恰好等于零件+余料）、旋转、超尺寸与超板数时的未排清单、
确定性、API 端到端与参数校验。

## 项目结构

```
app/
  nesting.py   # 直切排样引擎（纯 Python，无依赖）
  models.py    # Pydantic 请求/响应模型
  service.py   # 引擎结果 → API 响应组装
  db.py        # SQLite 初始化与存取
  main.py      # FastAPI 路由（启动时建表）
tests/         # pytest 测试
Dockerfile / docker-compose.yml / requirements*.txt
```
