#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 青龙面板备份脚本 (webdav4 版)
# cron: 30 3 * * *
#
# 功能：打包选中目录 -> 上传 WebDAV -> 按 CLEANUP_POLICY 清理云端旧备份
# 依赖：webdav4  (订阅后在依赖管理安装,或 pip install webdav4)
# 配置：全部环境变量及默认值见 .env.example
# 上传：重试次数/指数退避间隔由 common 的 UPLOAD_RETRY / UPLOAD_RETRY_DELAY 控制
# 订阅：ql repo <仓库地址> backup   (白名单 backup 同时匹配两个备份脚本)
#
# 【QL_BACKUP_INCLUDE 可填入别名，逗号分隔】别名映射清单：
#   base      → db, upload        基础数据：数据库、上传文件
#   config    → config            config.yaml、通知、面板密码证书
#   scripts   → scripts           自定义脚本文件
#   deps      → deps              sendNotify 等通知公共依赖脚本
#   repo      → repo              远程订阅仓库缓存（修改过仓库内文件才需要）
#   ssh.d     → ssh.d             SSH 密钥，用于 ssh 拉取仓库
#   dep_cache → dep_cache         Node/Python 包缓存（体积很大，按需选）
#   log       → log               运行日志
#   syslog    → syslog            青龙系统日志
#   raw       → raw               远程脚本临时缓存
#   bak       → bak               本地旧备份文件夹
#   db        → db                数据库目录（单独写也可以）
#   upload    → upload            上传目录（单独写也可以）
#   compose   → docker-compose.yml 宿主机编排文件，需要挂载 ./:/ql/host:ro
# 示例：QL_BACKUP_INCLUDE="base,config,deps,ssh.d,dep_cache,compose"
# ============================================================

import os
import sys
import tarfile
from common import (log, make_filename, make_tmp_file, env,
                    get_webdav_client, webdav_ensure_dir,
                    webdav_upload, webdav_cleanup)

# ===================== 别名映射表 =====================
NAME_MAP = {
    "base": ["db", "upload"],
    "config": ["config"],
    "scripts": ["scripts"],
    "log": ["log"],
    "deps": ["deps"],
    "syslog": ["syslog"],
    "dep_cache": ["dep_cache"],
    "raw": ["raw"],
    "repo": ["repo"],
    "ssh.d": ["ssh.d"],
    "bak": ["bak"],
    "db": ["db"],
    "upload": ["upload"],
    "compose": ["docker-compose.yml"]
}

# ---------- 环境变量 (青龙面板配置) ----------
RETENTION_DAYS = env('RETENTION_DAYS', 7, int)
RETENTION_COUNT = env('RETENTION_COUNT', 7, int)
CLEANUP_POLICY = env('CLEANUP_POLICY', 'both')
QL_DATA_DIR = env('QL_DATA_DIR', '/ql/data')
QL_BACKUP_INCLUDE = env('QL_BACKUP_INCLUDE', 'base,config')
# compose 文件不在 /ql/data 下,从宿主机挂载目录读取(需挂载 ./:/ql/host:ro)
HOST_DIR = env('QL_HOST_DIR', '/ql/host')

# WebDAV 客户端(基础地址在 WEBDAV_BASE_URL,备份目录 /qinglong)
client = get_webdav_client('/qinglong')


def resolve_include(raw: str) -> list:
    """把 QL_BACKUP_INCLUDE 的别名展开为 /ql/data 下的真实目录列表(排序去重)。"""
    include = set()
    for item in (s.strip() for s in raw.split(',')):
        if not item:
            continue
        if item not in NAME_MAP:
            log(f'[警告] 未知备份选项：{item}，跳过')
            continue
        include.update(NAME_MAP[item])
    return sorted(include)


INCLUDE_LIST = resolve_include(QL_BACKUP_INCLUDE)
if not INCLUDE_LIST:
    log('[错误] QL_BACKUP_INCLUDE 解析后为空，请检查配置')
    sys.exit(1)


def do_backup():
    """打包 INCLUDE_LIST 中的目录/文件(原样打包,无过滤),返回 (临时文件路径, 文件名)。"""
    filename = make_filename('qinglong', '.tar.gz', 'timestamp')
    tmp_file = make_tmp_file(filename)

    log('=== 开始备份青龙面板 ===')
    log(f'数据源: {QL_DATA_DIR}')
    log(f'输入别名: {QL_BACKUP_INCLUDE}')
    log(f'展开后列表: {INCLUDE_LIST}')

    if not os.path.isdir(QL_DATA_DIR):
        log(f'错误: {QL_DATA_DIR} 不存在')
        sys.exit(1)

    with tarfile.open(tmp_file, 'w:gz') as tar:
        for entry in INCLUDE_LIST:
            # compose 从宿主机挂载目录读取,其余都是 /ql/data 下的目录
            src = os.path.join(HOST_DIR if entry == 'docker-compose.yml' else QL_DATA_DIR, entry)
            if not os.path.exists(src):
                log(f'[警告] {src} 不存在，跳过')
                continue
            tar.add(src, arcname=entry)

    size_mb = os.path.getsize(tmp_file) / 1024 / 1024
    log(f'打包完成: {filename} ({size_mb:.1f} MB)')
    return tmp_file, filename


def upload(file_path, remote_name):
    """确保目录存在后上传(重试与退避由 common 的 webdav_upload 处理)。"""
    webdav_ensure_dir(client)
    log('上传到坚果云...')
    return webdav_upload(client, file_path, f"/{remote_name}")


def main():
    """备份 -> 上传 -> 清理,临时文件无论成败都删除。"""
    tmp_file, filename = do_backup()
    try:
        if not upload(tmp_file, filename):
            sys.exit(1)
        webdav_cleanup(client, RETENTION_DAYS, RETENTION_COUNT, policy=CLEANUP_POLICY)
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
    log('=== 青龙面板备份完成 ✓ ===')


if __name__ == '__main__':
    main()
