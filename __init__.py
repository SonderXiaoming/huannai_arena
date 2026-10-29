from collections import defaultdict
import traceback
from nonebot import on_startup
import contextlib
from os.path import dirname
from pathlib import Path
import time

from .constants import ArenaQueryType, RoleMasteryType
from .errorclass import UnRelatedError
from hoshino import Service
from .pic_recognize.dic import update_dic
from hoshino.typing import CQEvent, HoshinoBot
from hoshino.util import FreqLimiter
from .setting import db_config, mzq_config
from .database.migrate import migrate_arena_to_pgsql
from .database.sqla import arena_sqla
from .utils.arena import ArenaQuery
from .draw import render_atk_def_teams, render_matrix
from .query.mzq import mzq_query

sv_help = """
[怎么拆] 接防守队角色名 查询竞技场解法
[作业网查询] 接防守队角色名 只查询作业网解法
[竞技场模拟] 进攻队角色名vs防守队角色名
例子 竞技场模拟环奈春环千爱瑠银莲雪菲vs美空铃奈ams日和ue
[竞技场建议] 接防守队角色名 查询竞技场建议阵容 （模拟可能解法）
[#竞技场建议] 接防守队角色名 查询竞技场建议阵容 （不使用缓存的模拟结果）
[竞技场矩阵] 进攻队#进攻队 vs 防守队#防守队  批量两两模拟并以矩阵图返回胜率（不走缓存）
例子：竞技场矩阵 环奈春环千爱瑠银莲雪菲#美空铃奈ams日和ue vs 环奈春环千爱瑠银莲雪菲#美空铃奈ams日和ue
[#怎么拆] 开始连续图片查询竞技场解法
[结束查询] 结束连续图片查询
[竞技场更新卡池] 更新竞技场识别卡池
PS1：可以用“#” 表示分隔队伍
如：竞技场建议 环奈春环千爱瑠银莲雪菲#美空铃奈ams日和ue 查询多队解法
PS2：怎么拆和作业网查询支持指定区域查询 （支持b，台，日）
如：台作业网查询 接防守队角色名 查询台服作业网解法
""".strip()
sv = Service("huannai_arena", help_=sv_help, bundle="pcr查询")


lmt = FreqLimiter(5)
working_dir = Path(dirname(__file__))

aliases = ("怎么拆", "怎么解", "怎么打", "如何拆", "如何解", "如何打", "jjc查询", "jjc")
aliases_b = tuple(f"b{a}" for a in aliases) + tuple(f"B{a}" for a in aliases)
aliases_tw = tuple(f"台{a}" for a in aliases) + tuple(f"t{a}" for a in aliases)
aliases_jp = tuple(f"日{a}" for a in aliases) + tuple(f"r{a}" for a in aliases)

user_cache = {}


@on_startup
async def init_database():
    await arena_sqla.create_all()
    if db_config.migrate_to_pgsql:
        try:
            await migrate_arena_to_pgsql(db_config.arena_url, db_config.arena_pgsql_url)
        except Exception:
            traceback.print_exc()


@sv.on_fullmatch("竞技场对战帮助")
async def arena_query_help(bot: HoshinoBot, ev: CQEvent):
    await bot.send(ev, sv_help)


# 全服=1 b服=2 台服=3 日服=4
@sv.on_prefix(aliases)
@sv.on_prefix(aliases_b)
@sv.on_prefix(aliases_tw)
@sv.on_prefix(aliases_jp)
@sv.on_prefix((f"{a}作业网查询" for a in ("", "b", "台", "日")))
async def arena_query(bot: HoshinoBot, ev: CQEvent):
    if not lmt.check(ev.user_id):
        await bot.send(ev, "请求过于频繁，请稍后再试")
        return
    lmt.start_cd(ev.user_id)
    region = 1
    cmd = str(ev.prefix).strip()[0]
    if cmd in ("b", "B"):
        region = 2
    elif cmd in ("台", "t"):
        region = 3
    elif cmd in ("日", "r"):
        region = 4
    query = ArenaQuery(region, str(ev.message))
    allow = (ArenaQueryType.pcrfans,) if "作业网查询" in str(ev.raw_message) else None
    try:
        result, extra = await query.arena_query(allow=allow)
        if extra:
            with contextlib.suppress(Exception):
                await bot.send(ev, extra)
        if not result:
            await bot.send(ev, "未找到合适的解法，请尝试去pcrfans查询")
            return
        im = await render_atk_def_teams(result)
        await bot.send(ev, im)
    except UnRelatedError:
        return
    except Exception as e:
        traceback.print_exc()
        await bot.send(ev, f"查询出错：{e}")
        return


@sv.on_prefix("竞技场模拟")
async def arena_simulate_query(bot: HoshinoBot, ev: CQEvent):
    if not lmt.check(ev.user_id):
        await bot.send(ev, "请求过于频繁，请稍后再试")
        return
    lmt.start_cd(ev.user_id)
    region = 1
    cmd = str(ev.prefix).strip()[0]
    if cmd in ("b", "B"):
        region = 2
    elif cmd in ("台", "t"):
        region = 3
    elif cmd in ("日", "r"):
        region = 4
    query = ArenaQuery(2, str(ev.message))
    await bot.send(ev, "正在模拟对战，请稍候~")
    try:
        result, extra = await query.run_single_simulation()
        if not result:
            await bot.send(ev, "模拟对战失败，请稍后再试")
            return
        with contextlib.suppress(Exception):
            await bot.send(ev, extra)
        im = await render_atk_def_teams([result])
        await bot.send(ev, im)
    except Exception as e:
        traceback.print_exc()
        await bot.send(ev, f"查询出错：{e}")
        return


@sv.on_prefix("竞技场建议")
@sv.on_prefix("#竞技场建议")
async def arena_suggest_query(bot: HoshinoBot, ev: CQEvent):
    if not lmt.check(ev.user_id):
        await bot.send(ev, "请求过于频繁，请稍后再试")
        return
    lmt.start_cd(ev.user_id)
    region = 1
    cmd = str(ev.prefix).strip()[0]
    use_cache = cmd != "#"
    """if cmd in ("b", "B"):
        region = 2
    elif cmd in ("台", "t"):
        region = 3
    elif cmd in ("日", "r"):
        region = 4"""
    query = ArenaQuery(2, str(ev.message))
    await bot.send(ev, "正在查询，请稍候~")
    try:
        results, extra = await query.mzq_check(use_cache=use_cache)
        with contextlib.suppress(Exception):
            await bot.send(ev, extra)
        if not results:
            await bot.send(ev, "未找到合适的解法，请尝试去pcrfans查询")
            return
        im = await render_atk_def_teams(results)
        await bot.send(ev, im)
    except Exception as e:
        traceback.print_exc()
        await bot.send(ev, f"查询出错：{e}")
        return


@sv.on_prefix("竞技场矩阵")
async def arena_matrix_query(bot: HoshinoBot, ev: CQEvent):
    if not lmt.check(ev.user_id):
        await bot.send(ev, "请求过于频繁，请稍后再试")
        return
    lmt.start_cd(ev.user_id)
    query = ArenaQuery(2, str(ev.message))
    await bot.send(ev, "正在批量模拟，请稍候~")
    try:
        atk_list, def_list, matrix, extra = await query.matrix_simulate()
        if extra:
            with contextlib.suppress(Exception):
                await bot.send(ev, extra)
        im = await render_matrix(atk_list, def_list, matrix)
        await bot.send(ev, im)
    except Exception as e:
        traceback.print_exc()
        await bot.send(ev, f"查询出错：{e}")
        return


@sv.on_prefix(
    [f"#{aliase}" for aliase in (aliases + aliases_b + aliases_tw + aliases_jp)]
)
async def continue_arena_query(bot, ev):
    region = 1
    cmd = str(ev.prefix).strip()[0]
    if cmd in ("b", "B"):
        region = 2
    elif cmd in ("台", "t"):
        region = 3
    elif cmd in ("日", "r"):
        region = 4
    user_cache[(ev.user_id, ev.group_id)] = region, time.time()
    await bot.send(
        ev, "了解，请连续发送图片查询解法，记得使用【结束查询】来结束查询哦~"
    )


@sv.on_message("group")
async def reply_arena_query(bot, ev):
    if (ev.user_id, ev.group_id) not in user_cache:
        return
    region, timestamp = user_cache[(ev.user_id, ev.group_id)]
    if time.time() - timestamp < 60:
        if "CQ:image" in str(ev.message):
            query = ArenaQuery(region, str(ev.message))
            try:
                result, extra = await query.arena_query()
                if extra:
                    with contextlib.suppress(Exception):
                        await bot.send(ev, extra)
                if not result:
                    await bot.send(ev, "未找到合适的解法，请尝试去pcrfans查询")
                    return
                im = await render_atk_def_teams(result)
                await bot.send(ev, im)
            except Exception as e:
                await bot.send(ev, f"查询出错：{e}")
                return
            user_cache[(ev.user_id, ev.group_id)] = region, time.time()
    else:
        del user_cache[(ev.user_id, ev.group_id)]


@sv.on_fullmatch("结束查询")
async def end_arena_query(bot, ev):
    if (ev.user_id, ev.group_id) in user_cache:
        del user_cache[(ev.user_id, ev.group_id)]
        await bot.send(ev, "已结束查询")


@sv.on_fullmatch("竞技场模拟练度")
async def arena_simulate_lv(bot: HoshinoBot, ev: CQEvent):
    try:
        result = await mzq_query.get_default_development()
        role_mastery_dict = defaultdict(str)
        for k, v in mzq_config.default_progression.role_mastery.items():
            role = RoleMasteryType.from_value(k)
            role_mastery_dict[role.name] += f"{v[0]}-{v[1]};"
        role_mastery_str = "\n".join(
            [f"{k}：{v[:-1]}" for k, v in role_mastery_dict.items()]
        )
        await bot.send(
            ev,
            f"默认练度信息：\n玩家等级：{result.PlayerLevel}\n玩家品级：{result.PlayerRank}\n专武等级：{result.PlayerUniqueEqLv}\n属性等级：{result.TalentLevel}\n属性加点：{result.TalentSkill}\nmp：{result.TeamSkill}\n职能精通：\n{role_mastery_str}",
        )
    except Exception as e:
        await bot.send(ev, f"查询出错：{e}")
        return


@sv.on_fullmatch("竞技场更新卡池")
async def _update_dic(bot, ev):
    try:
        await bot.send(ev, f"{await update_dic()}")
    except Exception as e:
        await bot.send(ev, f"Error: {e}")


@sv.scheduled_job("cron", hour="3", minute="21")
async def _update_dic_cron():
    with contextlib.suppress(Exception):
        await update_dic()
