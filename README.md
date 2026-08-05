# FG-prediction-gateway · ForeGate 预测统一网关

**中文** · 一个对外入口,按 `type` 把请求分发到三套预测引擎(足球 / 篮球 / 电竞)。三个引擎各自是独立仓库、以 git 子模块引入;网关只做分发,不改任何模型逻辑,各引擎的 `markets` / `platform_markets` 原样透传。零依赖(仅 Python 标准库)。

**English** · One public entry that dispatches by `type` to three prediction engines (football / basketball / esports). Each engine is an independent repo brought in as a git submodule; the gateway only routes — model logic untouched — and passes each engine's `markets` / `platform_markets` through verbatim. Zero-dependency (Python stdlib only).

---

## 架构 / Architecture

```
FG-prediction-gateway
├── gateway.py                 # 反向代理:按 type 转发,聚合 /health
├── engines/football    →  submodule: FG-football-prediction
├── engines/basketball  →  submodule: FG-basketball-prediction
└── engines/esports     →  submodule: FG-esports-prediction
```

启动时把三个引擎各自的 `server.py` 作为子进程拉起在内部端口(127.0.0.1:8101/8102/8103),网关监听 `$PORT`,按 `type` 去掉该参数后把**原路径 + 其余查询串**转发给对应引擎,原样回传。引擎代码零改动。

On startup the three engines' `server.py` run as child processes on internal ports; the gateway listens on `$PORT`, strips `type`, and forwards the original path + remaining query to the right engine, returning its response unchanged.

---

## HTTP API

| 路由 Route | 说明 |
|---|---|
| `GET /ping` | 超轻保活探测(唤醒瞬间即 200)· ultra-light keep-alive |
| `GET /health` | 聚合三引擎健康状态 · aggregated health |
| `GET /predict?type=football&categoryId=30118&a=Arsenal&b=Chelsea` | 足球预测 |
| `GET /predict?type=basketball&categoryId=30163&a=Lakers&b=Celtics` | 篮球预测 |
| `GET /predict?type=esports&game=lol&a=T1&b=Gen.G&bo=5` | 电竞预测 |

`type`(或 `sport`)取值:`football` / `basketball` / `esports`(含 `soccer`、`nba`、`esport` 等别名)。
去掉 `type` 后的其余参数与路径**原样透传**给对应引擎,所以各引擎原有的参数与路由都可用:

- 足球 / 篮球:`categoryId`(平台联赛 id)/ `code` / `name`,`a`、`b`,`lang`,可选赔率;另有 `/competitions`、`/teams`。
- 电竞:`game`(lol/dota2/cs2/...)/ `categoryId` / `name`,`a`、`b`,`bo`(几局几胜),`lang`;另有 `/games`、`/stats`。

示例 · Example:

```bash
curl "$BASE/predict?type=basketball&categoryId=30163&a=Lakers&b=Celtics&lang=en"
curl "$BASE/predict?type=esports&game=lol&a=T1&b=Gen.G&bo=5"
```

返回体即对应引擎的原始返回(含 `markets`,足球/篮球另含 `platform_markets`)。
The response is the engine's own payload (`markets`, plus `platform_markets` for football/basketball).

---

## 部署 / Deploy

Render → New → Blueprint 连接本仓库(读 `render.yaml`,免费档)。**务必开启子模块拉取**(Render 默认会对公开子模块执行 `git submodule update --init`)。启动命令 `python3 gateway.py` 会自动拉起三个引擎子进程。

Render → New → Blueprint on this repo (`render.yaml`, free plan). **Ensure submodule checkout is on** (Render inits public submodules by default). `python3 gateway.py` launches the three engine subprocesses.

**数据更新 / Data freshness**:三个引擎各自的仓库照常每日刷新(各自的 Secret 与 workflow 不变)。本网关的 `.github/workflows/sync-engines.yml` 每日把三个子模块指针更新到各自最新提交并推送,Render 随即自动重部署,即拿到最新快照。**本网关不直接调用任何数据 API、无需任何 Secret。**

The three engine repos keep their own daily refresh (their own secrets/workflows unchanged). This gateway's daily workflow bumps the submodule pointers to each engine's latest commit and pushes; Render auto-redeploys with fresh snapshots. **The gateway calls no data API and needs no secrets.**

---

## 平滑切换 / Cutover

三个旧的独立服务保持不动;平台准备好后,前端从"三个旧地址"改为"一个网关地址 + `type`"即可一次性切换,验证无误后再从容下线旧服务。回滚只需切回旧地址。

The three legacy services stay live; when ready, the platform switches the frontend to this one gateway URL (+ `type`) in a single upgrade, then retires the old endpoints at leisure. Rollback = point back to the old URLs.

## License
MIT
