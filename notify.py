#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 通用通知脚本 (多平台,按渠道分发)
# cron: 可不配 cron,作为其他脚本结尾调用;也可配定时用于测试连通性
#
# 功能：统一的通知入口,内部按渠道分发到具体平台。当前已实现:
#   qywx - 企业微信群机器人 webhook
# 扩展：新增平台只需写一个 send_xxx 函数并加 @register 装饰器,
#       调用方无需改动(见文件末尾"新增渠道示例")
#
# 依赖：requests  (订阅后在依赖管理安装,或 pip install requests)
# 配置：
#   NOTIFY_CHANNEL      默认渠道,不传 -c 时使用,默认 qywx
#   QYWX_WEBHOOK        企微群机器人 webhook,支持完整地址或仅填 key
#   NOTIFY_RETRY        失败重试次数,默认 3
#   NOTIFY_RETRY_DELAY  重试基础间隔秒,默认 3 (指数退避)
#
# 用法：
#   python3 notify.py "测试消息"                       # 默认渠道,markdown
#   python3 notify.py -c qywx -t text "纯文本消息"     # 指定渠道与消息类型
#   python3 notify.py -c qywx -T "标题" "内容"
#   echo "内容" | python3 notify.py                    # 从管道读内容
#   python3 notify.py --list                           # 查看已支持渠道
#   其他脚本调用：
#     from notify import send
#     send('任务通知', '**备份完成**\n> 共 3 个文件')
#     send('任务通知', '内容', channel='qywx')
# ============================================================

import argparse
import sys
import time

import requests

from common import env, log

# ---------- 环境变量 (青龙面板配置) ----------
NOTIFY_RETRY = env('NOTIFY_RETRY', 3, int)
NOTIFY_RETRY_DELAY = env('NOTIFY_RETRY_DELAY', 3, int)


class Channel:
    """一个通知渠道的元信息 + 发送实现。"""

    def __init__(self, name: str, desc: str, required_env, func):
        self.name = name
        self.desc = desc
        self.required_env = list(required_env)
        self.func = func


CHANNELS = {}


def register(name: str, desc: str, required_env=()):
    """装饰器：把 send_xxx 函数注册为可用的通知渠道。

    name:         渠道标识,命令行 -c 与 send(channel=) 使用
    desc:         渠道说明,用于 --list
    required_env: 该渠道必需的环境变量,发送前统一校验
    """
    def deco(func):
        CHANNELS[name] = Channel(name, desc, required_env, func)
        return func
    return deco


def _post_json(url: str, body: dict, ok_check, timeout: int = 15):
    """POST JSON 并按 ok_check 判断业务成功,失败自动重试(指数退避)。

    返回 (成功与否, 最后一次响应 dict 或 None)。重试次数/间隔取环境变量。
    """
    data = None
    for attempt in range(NOTIFY_RETRY + 1):
        try:
            resp = requests.post(url, json=body, timeout=timeout)
            data = resp.json()
            if ok_check(data):
                return True, data
            log(f'接口返回异常: {data}')
        except Exception as e:
            log(f'第 {attempt + 1} 次请求失败: {str(e)}')
        if attempt >= NOTIFY_RETRY:
            break
        wait = NOTIFY_RETRY_DELAY * (2 ** attempt)
        log(f'等待{wait}秒后重试...')
        time.sleep(wait)
    return False, data


# ===================== 渠道：企业微信 =====================
QYWX_WEBHOOK_BASE = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send'


def _qywx_webhook_url() -> str:
    """把 QYWX_WEBHOOK 归一化为完整 webhook 地址。"""
    value = env('QYWX_WEBHOOK', '')
    if value.startswith(('http://', 'https://')):
        return value
    return f'{QYWX_WEBHOOK_BASE}?key={value}'


@register('qywx', '企业微信群机器人', ['QYWX_WEBHOOK'])
def send_qywx(title: str, content: str, msg_type: str = 'markdown') -> bool:
    """推送企业微信群机器人消息。

    msg_type: text 或 markdown;text 自动带标题,markdown 标题加粗放首行
    """
    if msg_type not in ('text', 'markdown'):
        raise ValueError(f'未知消息类型: {msg_type}，可选 text/markdown')

    if msg_type == 'text':
        text = f'{title}\n{content}' if content else title
        body = {'msgtype': 'text', 'text': {'content': text}}
    else:
        md = f'**{title}**\n{content}' if content else f'**{title}**'
        body = {'msgtype': 'markdown', 'markdown': {'content': md}}

    ok, _ = _post_json(_qywx_webhook_url(), body,
                       lambda d: d.get('errcode') == 0)
    log('企微通知发送成功' if ok else '企微通知发送失败')
    return ok


# 兼容旧调用名
send_wechat_work = send_qywx


# ===================== 统一入口 =====================
def send(title: str = '通知', content: str = '',
         channel: str = None, **kwargs) -> bool:
    """按渠道发送通知,返回是否成功。

    channel 为空时取环境变量 NOTIFY_CHANNEL,再缺省为 qywx。
    kwargs 透传给具体渠道(如 qywx 的 msg_type)。
    """
    name = channel or env('NOTIFY_CHANNEL', 'qywx')
    ch = CHANNELS.get(name)
    if not ch:
        raise ValueError(f'不支持的通知渠道: {name}，可选: {"/".join(CHANNELS)}')

    missing = [key for key in ch.required_env if not env(key)]
    if missing:
        raise RuntimeError(f'渠道 {name} 缺少环境变量: {", ".join(missing)}')

    log(f'=== 发送通知 [渠道 {name} / {ch.desc}] ===')
    return ch.func(title, content, **kwargs)


def main():
    parser = argparse.ArgumentParser(description='通用通知脚本(多平台可扩展)')
    parser.add_argument('-c', '--channel', default=None,
                        help='通知渠道,默认取 NOTIFY_CHANNEL 或 qywx')
    parser.add_argument('-t', '--type', default='markdown',
                        choices=['text', 'markdown'], help='消息类型,默认 markdown')
    parser.add_argument('-T', '--title', default='青龙通知', help='消息标题')
    parser.add_argument('--list', action='store_true', help='列出已支持的渠道')
    parser.add_argument('content', nargs='?', default='',
                        help='消息内容,留空则从标准输入读取')
    args = parser.parse_args()

    if args.list:
        for ch in CHANNELS.values():
            env_hint = f" (需要 {', '.join(ch.required_env)})" if ch.required_env else ''
            print(f'{ch.name:<10} {ch.desc}{env_hint}')
        return

    content = args.content
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read().strip()
    if not content:
        content = '这是一条来自青龙面板的测试通知 ✅'

    ok = send(args.title, content, channel=args.channel, msg_type=args.type)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()


# ===================== 新增渠道示例 =====================
# 以钉钉机器人为例,复制下面的骨架并填入实现即可,调用方无需改动:
#
# @register('dingtalk', '钉钉群机器人', ['DINGTALK_WEBHOOK'])
# def send_dingtalk(title, content, msg_type='markdown'):
#     body = {'msgtype': 'markdown',
#             'markdown': {'title': title, 'text': f'### {title}\n{content}'}}
#     ok, _ = _post_json(env('DINGTALK_WEBHOOK'), body,
#                        lambda d: d.get('errcode') == 0)
#     log('钉钉通知发送成功' if ok else '钉钉通知发送失败')
#     return ok
