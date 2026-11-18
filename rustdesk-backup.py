#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# RustDesk 备份脚本 (青龙面板 webdav4 版)
# cron: 40 3 * * *
#
# 功能：打包 docker-compose.yml + data + api_data(排除日志) -> 上传 WebDAV -> 清理旧备份
# 依赖：webdav4  (订阅后在依赖管理安装,或 pip install webdav4)
# 挂载：rustdesk 目录挂到容器内 /source/rustdesk，或用 RUSTDESK_DIR 指定
# 配置：全部环境变量及默认值见 .env.example
# 订阅：ql repo <仓库地址> backup   (白名单 backup 同时匹配两个备份脚本)
# ============================================================

import os
import sys
import tarfile
from common import (log, make_filename, make_tmp_file, env,
                    format_size, get_dir_size,
                    get_webdav_client, webdav_ensure_dir,
                    webdav_upload, webdav_cleanup)

# ---------- 环境变量 (青龙面板配置) ----------
RETENTION_DAYS = env('RETENTION_DAYS', 7, int)
RETENTION_COUNT = env('RETENTION_COUNT', 7, int)
CLEANUP_POLICY = env('CLEANUP_POLICY', 'both')
RUSTDESK_DIR = env('RUSTDESK_DIR', '/source/rustdesk')

# WebDAV 客户端(基础地址在 WEBDAV_BASE_URL,备份目录 /rustdesk)
client = get_webdav_client('/rustdesk')


def tar_filter(tarinfo):
    """打包过滤：排除日志文件和日志目录。"""
    name = tarinfo.name
    if name.endswith('.log') or '/log/' in name or name.startswith('log/'):
        return None
    return tarinfo


def do_backup():
    """打包 compose + data + api_data,小于 1KB 的空包拦截不上传,返回 (临时文件路径, 文件名)。"""
    filename = make_filename('rustdesk', '.tar.gz', 'timestamp')
    tmp_file = make_tmp_file(filename)

    log('=== 开始备份 RustDesk ===')
    log(f'数据源: {RUSTDESK_DIR}')

    if not os.path.isdir(RUSTDESK_DIR):
        log(f'错误: {RUSTDESK_DIR} 不存在, 请检查挂载')
        sys.exit(1)

    # (源路径, 包内路径, 是否目录)
    targets = [
        (os.path.join(RUSTDESK_DIR, 'docker-compose.yml'), 'docker-compose.yml', False),
        (os.path.join(RUSTDESK_DIR, 'data'), 'data', True),
        (os.path.join(RUSTDESK_DIR, 'api_data'), 'api_data', True),
    ]

    with tarfile.open(tmp_file, 'w:gz') as tar:
        for src, arcname, is_dir in targets:
            # 先确认存在再算大小,缺失时跳过而不是崩溃
            if is_dir:
                if not os.path.isdir(src):
                    log(f'[警告] 目录 {src} 不存在，跳过')
                    continue
                log(f'📂 {arcname} 目录总大小：{format_size(get_dir_size(src))}')
                tar.add(src, arcname=arcname, filter=tar_filter)
            else:
                if not os.path.isfile(src):
                    log(f'[警告] 文件 {src} 不存在，跳过')
                    continue
                log(f'📄 {arcname} 大小：{format_size(os.path.getsize(src))}')
                tar.add(src, arcname=arcname)
            log(f'✅ 已加入：{arcname}')

    file_bytes = os.path.getsize(tmp_file)
    log(f'打包完成: {filename} ({format_size(file_bytes)})')

    # 空包拦截：小于 1KB 视为空备份，终止任务且不上传
    if file_bytes < 1024:
        log('❌ 警告：打包文件过小，是空备份！终止任务，不上传')
        os.remove(tmp_file)
        sys.exit(1)

    return tmp_file, filename


def upload(file_path, remote_name):
    """确保目录存在后上传(重试与退避由 common 的 webdav_upload 处理)。"""
    webdav_ensure_dir(client)
    log('上传到坚果云...')
    return webdav_upload(client, file_path, f"/{remote_name}")


def main():
    """备份 -> 上传 -> 清理，临时文件无论成败都删除。"""
    tmp_file, filename = do_backup()
    try:
        if not upload(tmp_file, filename):
            sys.exit(1)
        webdav_cleanup(client, RETENTION_DAYS, RETENTION_COUNT, policy=CLEANUP_POLICY)
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
    log('=== RustDesk 备份完成 ✓ ===')


if __name__ == '__main__':
    main()
