#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 企业微信通知脚本 (webhook 机器人版)
# cron: 可不配 cron,作为其他脚本结尾调用;也可配定时用于测试连通性
#
# 功能：通过企业微信群机器人 webhook 推送 text / markdown 消息
# 依赖：requests  (订阅后在依赖管理安装,或 pip install requests)
# 配置：环境变量 QYWX_WEBHOOK 配置群机器人的 webhook 地址
#       支持完整地址或仅填 key:
#         QYWX_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx
#         QYWX_WEBHOOK=xxxx
# 用法：
#   python3 qywx-notify.py "测试消息"                     # markdown 消息
#   python3 qywx-notify.py -t text "纯文本消息"           # text 消息
#   python3 qywx-notify.py -T "标题" "内容"               # 指定标题
#   echo "内容" | python3 qywx-notify.py                  # 从管道读内容
#   其他脚本调用：
#     from qywx_notify import send_wechat_work
#     send_wechat_work('任务通知', '**备份完成**\n> 共 3 个文件')
# ============================================================

import argparse
import sys
import time

import requests

from common import env, log

# ---------- 环境变量 (青龙面板配置) ----------
QYWX_WEBHOOK = env('QYWX_WEBHOOK', '')
# 失败重试次数与基础间隔(指数退避),与备份脚本保持一致
NOTIFY_RETRY = env('NOTIFY_RETRY', 3, int)
NOTIFY_RETRY_DELAY = env('NOTIFY_RETRY_DELAY', 3, int)

WEBHOOK_BASE = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send'


def resolve_webhook() -> str:
    """把 QYWX_WEBHOOK 归一化为完整 webhook 地址。"""
    if not QYWX_WEBHOOK:
        raise RuntimeError('请在环境变量配置 QYWX_WEBHOOK (企业微信群机器人 webhook 地址或 key)')
    if QYWX_WEBHOOK.startswith(('http://', 'https://')):
        return QYWX_WEBHOOK
    return f'{WEBHOOK_BASE}?key={QYWX_WEBHOOK}'


def send_wechat_work(title: str = '青龙通知', content: str = '',
                     msg_type: str = 'markdown') -> bool:
    """推送企业微信消息,失败自动重试(指数退避),返回是否成功。

    msg_type: text 或 markdown
    text 类型自动带上标题;markdown 类型标题加粗放在首行
    """
    webhook = resolve_webhook()
    if msg_type not in ('text', 'markdown'):
        raise ValueError(f'未知消息类型: {msg_type}，可选 text/markdown')

    if msg_type == 'text':
        text = f'{title}\n{content}' if content else title
        body = {'msgtype': 'text', 'text': {'content': text}}
    else:
        md = f'**{title}**\n{content}' if content else f'**{title}**'
        body = {'msgtype': 'markdown', 'markdown': {'content': md}}

    for attempt in range(NOTIFY_RETRY + 1):
        try:
            resp = requests.post(webhook, json=body, timeout=15)
            data = resp.json()
            if data.get('errcode') == 0:
                log(f'企微通知发送成功（第 {attempt + 1} 次尝试）' if attempt else '企微通知发送成功')
                return True
            log(f"企微通知发送失败: errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
        except Exception as e:
            log(f'第 {attempt + 1} 次发送失败: {str(e)}')
        if attempt >= NOTIFY_RETRY:
            log('已用尽重试次数，企微通知发送失败')
            return False
        wait = NOTIFY_RETRY_DELAY * (2 ** attempt)
        log(f'等待{wait}秒后重试...')
        time.sleep(wait)
    return False


def main():
    parser = argparse.ArgumentParser(description='企业微信群机器人通知脚本')
    parser.add_argument('-t', '--type', choices=['text', 'markdown'],
                        default='markdown', help='消息类型,默认 markdown')
    parser.add_argument('-T', '--title', default='青龙通知', help='消息标题')
    parser.add_argument('content', nargs='?', default='',
                        help='消息内容,留空则从标准输入读取')
    args = parser.parse_args()

    content = args.content
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read().strip()
    if not content:
        content = '这是一条来自青龙面板的测试通知 ✅'

    log(f'=== 开始发送企业微信通知 [{args.type}] ===')
    ok = send_wechat_work(args.title, content, args.type)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
