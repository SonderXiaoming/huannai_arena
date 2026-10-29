# 竞技场建议

《HoshinoBot 公主连结竞技场查询与模拟对战插件》

★ 如果你喜欢的话，请给仓库点一个 Star 支持一下 23333 ★

本项目地址：
https://github.com/SonderXiaoming/huannai_arena

## 先看这里

**本插件和普通的 `arena` 插件冲突，请勿同时启用。** `怎么拆`、`jjc`、图片查询、`竞技场更新卡池` 等指令有重叠，同时加载可能重复回复或互相干扰。部署前请关闭原来的竞技场查询插件，包括 Hoshino 自带或改版的 `priconne/arena`、独立的 `arena` 等；如果它是被其他模块导入的，也要关闭对应的加载入口。

**本插件依赖摸轴器的模拟对战 API，下载插件后还需要配置服务端。** 摸轴器目前还没有开源，但即将开源。之前一直没有开源这个插件，也是因为摸轴器没开源，插件给了大家也用不了；现在摸轴器即将开源，于是也就一起开源了。

目前如果是**非盈利、小规模 bot**，可以找我申请 API：

- QQ：**1316864423**
- 或者在 Hoshino 群找一个叫**雨中流浪汉**的。

**摸轴器后续开源后，请自行部署服务端。** 本仓库不包含摸轴器服务端，也不附带公共 API 地址或密钥。

## 原理与功能

原理就是**让摸轴器模拟对战**：从作业网和本地记录中收集可能的进攻阵容，再交给摸轴器重复模拟，统计胜率后返回建议。并不是遍历所有角色组合，也不是拿到实战录像后反推解法。

- 竞技场建议：模拟候选解法，默认复用有效的模拟缓存。
- 竞技场模拟：指定进攻队和防守队，直接模拟对战。
- 竞技场矩阵：多支进攻队与多支防守队两两模拟，以矩阵图显示胜率。
- 普通查询：作业网查询、本地模拟记录查询、图片识别和多队无冲配队。
- 默认每组模拟 10 次；结果受摸轴器版本、游戏数据和默认练度影响，胜率仅供参考。

模拟相关指令目前按国服（B 服）区域处理；作业网查询支持全服、B 服、台服、日服。

## 部署教程

### 1. 下载插件、安装依赖

需要已有可用的 HoshinoBot / NoneBot 1 环境，Python 3.10 及以上。在 `HoshinoBot/hoshino/modules` 目录执行：

```bash
git clone https://github.com/SonderXiaoming/huannai_arena.git
cd huannai_arena
python -m pip install -r requirements.txt
```

角色名解析、头像和点赞图标使用 Hoshino 的 `priconne` 资源，请先准备好角色别名与对应图片资源。

### 2. 配置摸轴器和游戏数据库

复制 `config.example.json` 为 `config.json`，然后填写：

```json
{
  "mzq": {
    "api": ["http://127.0.0.1:8888"],
    "client_key": "",
    "timeout": 10
  },
  "database": {
    "use_pgsql": false,
    "arena_pgsql_url": "",
    "migrate_to_pgsql": false
  }
}
```

- `mzq.api`：自己部署或申请到的摸轴器服务根地址，支持填写多个地址并依次重试。示例中的本机地址需要你自行部署服务后才能使用。
- `mzq.client_key`：服务端需要鉴权时填写，通过 `X-Client-Key` 请求头发送。
- `mzq.timeout`：每组请求的基础超时时间（秒），批量请求按组数放大。

插件另外需要公主连结的 SQLite 游戏数据库，默认读取 `resources/data/pcr_data.db`。请自行准备与所用版本匹配、至少包含 `unit_data`、`unit_talent` 表的数据库；本仓库不附带游戏数据库。

如果已有 `pcr_wiki` 或其他来源的游戏数据库，可以在 `config.json` 的 `database` 中增加 `pcr_url`，直接使用已有文件：

```json
"pcr_url": "sqlite+aiosqlite:////absolute/path/to/pcr_cn.db"
```

Windows 绝对路径示例为 `sqlite+aiosqlite:///D:/HoshinoBot/data/pcr_cn.db`。请自行更新游戏数据库，`pcr_update_path` 目前只是预留配置，不会自动下载数据。

`config.json` 已加入忽略规则，请把实际地址、密钥和数据库密码放在这里，勿提交到仓库。未配置摸轴器 API 时，仍可使用作业网查询；模拟相关功能需要先配置 API。

### 3. 数据库选择：数据量大推荐 PostgreSQL

**本插件支持 PostgreSQL。默认使用 SQLite，但 SQLite 在数据量大时比较慢，模拟记录多或查询量大的开发者建议使用 PostgreSQL。**

默认的竞技场记录库是 `resources/data/arena.db`，启动时自动建表。它与上面的公主连结游戏数据库用途不同；切换 PostgreSQL 只影响竞技场记录和缓存，游戏数据仍从 `pcr_url` 指定的 SQLite 库读取。

使用 PostgreSQL 时，先创建好数据库和用户，然后安装驱动：

```bash
python -m pip install -r requirements-pgsql.txt
```

在 `config.json` 的 `database` 中配置：

```json
{
  "use_pgsql": true,
  "arena_pgsql_url": "postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/huannai_arena",
  "migrate_to_pgsql": false,
  "arena_pool_size": 10,
  "arena_max_overflow": 20,
  "arena_pool_timeout": 60
}
```

请替换 `USER`、`PASSWORD` 和数据库地址；用户名、密码含特殊字符时请做 URL 编码。连接池参数可按实际负载调整。

已有 SQLite 数据需要迁移时，先备份并暂停机器人的写入，确认 `arena_url` 指向原来的 SQLite 库，再把 `migrate_to_pgsql` 设为 `true` 后启动一次，或在插件目录执行：

```bash
python database/migrate.py
```

迁移会按表分批复制，目标表已有数据时会跳过该表，不会合并或覆盖。完成后将 `migrate_to_pgsql` 改回 `false`；迁移失败时请查看日志并检查目标库是否已有部分数据，再决定如何处理。

### 4. 启用插件

在 Hoshino 配置文件（通常是 `hoshino/config/__bot__.py` 或 `hoshino/config/bot.py`）的 `MODULES_ON` 中加入：

```python
"huannai_arena",
```

再次确认已关闭普通 `arena`，然后重启 HoshinoBot。首次使用图片查询前发送 `竞技场更新卡池`，根据本机的角色头像生成识别库；之后每天 03:21 定时更新，时间以机器人进程配置为准。

## 指令

| 指令 | 说明 |
| --- | --- |
| `竞技场对战帮助` | 查看帮助 |
| `怎么拆 防守队角色名` | 查询作业网与本地模拟记录，也支持防守队截图 |
| `作业网查询 防守队角色名` | 只查询作业网 |
| `竞技场建议 防守队角色名` | 模拟候选阵容，使用有效缓存 |
| `#竞技场建议 防守队角色名` | 重新模拟候选阵容，不复用模拟缓存 |
| `竞技场模拟 进攻队vs防守队` | 指定双方阵容模拟对战 |
| `竞技场矩阵 进攻队#进攻队 vs 防守队#防守队` | 批量两两模拟，返回胜率矩阵，不复用缓存 |
| `#怎么拆` | 开始连续图片查询，随后连续发送截图 |
| `结束查询` | 结束连续图片查询 |
| `竞技场模拟练度` | 查询摸轴器默认练度与本地设定的职能精通 |
| `竞技场更新卡池` | 更新图片识别卡池 |

例子：

```text
竞技场建议 环奈春环千爱瑠银莲雪菲
竞技场建议 环奈春环千爱瑠银莲雪菲#美空铃奈ams日和ue
竞技场模拟 环奈春环千爱瑠银莲雪菲vs美空铃奈ams日和ue
台作业网查询 美空铃奈ams日和ue
```

角色名或别名以你自己的 Hoshino 词库为准。`#` 用来分隔队伍，多队查询最多 3 队，矩阵两边各最多 8 队。作业网查询可加 `b`、`台`、`日` 前缀指定区域。模拟请提供完整的 5 人阵容；不使用缓存或批量模拟的请求较多，请按服务端承载能力使用。

## 说明

1. 默认练度相关设置在 `setting.py` 的 `DefaultProgressionConfig`，请按摸轴器和游戏版本调整。
2. 游戏数据缺角色、角色头像没有更新或别名缺失，都可能影响查询和图片识别。
3. 作业网接口或摸轴器服务波动时可能查询失败，稍后重试即可。
4. 本仓库只发布插件源码和必要的渲染资源，不发布本地配置、数据库、识别缓存或历史查询记录。
5. 有 bug 可以提 issue，最好直接 PR；也可以 QQ 或 Hoshino 群找雨中流浪汉。

开发者可在插件目录运行本地检查，不需要连接摸轴器或真实数据库：

```bash
python -m unittest discover -s tests -v
```

## 项目参考

- [HoshinoBot](https://github.com/Ice-Cirno/HoshinoBot)：机器人框架、角色解析与资源支持。
- [pcrdfans](https://www.pcrdfans.com/)：竞技场作业查询。
- Hoshino 的 arena 与图片查询改版：查询交互、头像识别及渲染参考。
- 摸轴器：模拟对战服务端，当前尚未开源，开源后请自行部署。

代码沿用 HoshinoBot 的 GPL-3.0 许可证；字体与图片资源说明见 [NOTICE.md](NOTICE.md)。
