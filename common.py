# -*- coding: utf-8 -*-
"""通用工具函数:日志 + 文件名生成 + 临时文件路径 + 环境变量读取 + 大小格式化 + WebDAV 通用操作。"""
import os
import posixpath
import re
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def env(key: str, default=None, cast=str):
    """读取环境变量,可带默认值也可不带,支持类型转换(如 int)。
    未设置或为空字符串时返回 default。
    """
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    try:
        return cast(value)
    except Exception as e:
        raise RuntimeError(f"环境变量 {key} 转换失败，原始值：{value}，目标类型：{cast.__name__}") from e


def make_tmp_file(filename: str) -> str:
    """返回系统临时目录下指定文件名的完整路径。"""
    return os.path.join(tempfile.gettempdir(), filename)


def make_filename(prefix: str = "", ext: str = "", strategy: str = "both") -> str:
    """生成文件名(不含目录)。

    prefix: 可选前缀,非法字符会被替换为 _
    ext:    扩展名,如 ".log"、"txt" 均可,留空则不带扩展名
    """
    prefix = re.sub(r'[\\/:*?"<>|\s]+', "_", prefix.strip())
    ext = ext.strip().lstrip(".")
    ext = f".{ext}" if ext else ""

    if strategy == "timestamp":
        # 精确到秒,单进程内基本不重复
        core = datetime.now().strftime("%Y%m%d%H%M%S")
    elif strategy == "uuid":
        core = uuid.uuid4().hex[:12]  # 12位十六进制,约47位随机度
    else:  # both
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        core = f"{ts}_{uuid.uuid4().hex[:6]}"

    return f"{prefix}_{core}{ext}" if prefix else f"{core}{ext}"


def unique_filename(directory: str, prefix: str = "", ext: str = "",
                    strategy: str = "both", max_retry: int = 5) -> str:
    """生成文件名并确保在 directory 中不存在,返回完整路径。"""
    for i in range(max_retry):
        name = make_filename(prefix, ext, strategy)
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            return path
        # 万一撞名,自动加序号
        filename, extension = os.path.splitext(name)
        name = f"{filename}_{i + 1}{extension}"
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            return path
    raise RuntimeError("无法生成唯一文件名,请检查目录")


def get_dir_size(path):
    """递归计算目录总大小(字节),不跟随符号链接。"""
    total = 0
    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False):
            total += entry.stat(follow_symlinks=False).st_size
        elif entry.is_dir(follow_symlinks=False):
            total += get_dir_size(entry.path)
    return total


def format_size(byte_size):
    """字节数自动格式化为 B / KB / MB。"""
    if byte_size < 1024:
        return f"{byte_size} B"
    if byte_size < 1024 ** 2:
        return f"{byte_size / 1024:.2f} KB"
    return f"{byte_size / 1024 ** 2:.2f} MB"


# ===================== WebDAV 通用 =====================
def _join_url(base: str, path: str) -> str:
    """用标准库把路径拼接到 URL 后,如 base + /qinglong -> .../dav/qinglong。

    保留 base 的查询参数和锚点;path 为空时保留目录语义(尾部斜杠)。
    """
    parts = urlsplit(base)
    if path == '':
        # 空 path 等价 posixpath.join(x, '') 的语义:保留尾部斜杠
        new_path = posixpath.normpath(parts.path or '/') + '/'
    else:
        # posixpath.join 遇到以 / 开头的参数会丢弃前半段,需先去掉前导斜杠;
        # base 路径为空(纯域名)时按根 / 处理,同时把 ../ 跳转钳制在根内
        new_path = posixpath.normpath(
            posixpath.join(parts.path or '/', path.lstrip('/')))
    if not new_path.startswith('/'):
        new_path = '/' + new_path
    return urlunsplit(parts._replace(path=new_path))


def get_webdav_client(remote_path: str = '',
                      url_key: str = 'WEBDAV_BASE_URL',
                      user_key: str = 'WEBDAV_USER',
                      pass_key: str = 'WEBDAV_PASS',
                      timeout_key: str = 'WEBDAV_TIMEOUT',
                      default_timeout: int = 60):
    """从环境变量读取 WebDAV 配置并创建 webdav4 客户端。

    WEBDAV_BASE_URL 环境变量: 服务基础地址,如 https://dav.jianguoyun.com/dav
    remote_path: 备份目录,传路径(如 /qinglong)则拼接到 BASE_URL 后;
                 传完整 URL(以 http 开头)则直接使用。
    账号密码缺失或基础地址无法确定时抛 RuntimeError。
    """
    from webdav4.client import Client  # 延迟导入,不用 webdav 的脚本也能 import common
    user = env(user_key)
    password = env(pass_key)
    if not user or not password:
        raise RuntimeError(f'请在环境变量配置 {user_key} 和 {pass_key}')
    base = env(url_key)
    if remote_path.startswith(('http://', 'https://')):
        url = remote_path
    elif base and remote_path:
        url = _join_url(base, remote_path)
    elif base:
        url = base
    else:
        raise RuntimeError(f'请在环境变量配置 {url_key}')
    return Client(url, auth=(user, password),
                  timeout=env(timeout_key, default_timeout, int))


def webdav_ensure_dir(client, path: str = "/"):
    """确保 WebDAV 目录存在,目录已存在(HTTPError)时忽略。"""
    from webdav4.client import HTTPError
    try:
        client.mkdir(path)
    except HTTPError:
        pass


def webdav_upload(client, local_path: str, remote_path: str,
                  retry: int = None, base_delay: int = None) -> bool:
    """上传文件到 WebDAV,失败自动重试(指数退避),返回是否成功。

    retry:      重试次数,默认读环境变量 UPLOAD_RETRY(默认3),0 表示只试一次
    base_delay: 重试基础间隔秒数,默认读环境变量 UPLOAD_RETRY_DELAY(默认3)
                第 n 次重试等待 base_delay * 2^(n-1) 秒,如 3,6,12,24...
    """
    if retry is None:
        retry = env('UPLOAD_RETRY', 3, int)
    if base_delay is None:
        base_delay = env('UPLOAD_RETRY_DELAY', 3, int)
    for attempt in range(retry + 1):
        try:
            client.upload_file(local_path, remote_path)
            log(f'上传成功（第 {attempt+1} 次尝试）' if retry else '上传成功')
            return True
        except Exception as e:
            log(f'第 {attempt+1} 次上传失败: {str(e)}')
            if attempt >= retry:
                log('已用尽重试次数，上传失败' if retry else '上传失败')
                return False
            wait = base_delay * (2 ** attempt)
            log(f'等待{wait}秒后重试...')
            time.sleep(wait)
    return False


def webdav_cleanup(client, retention_days: int, retention_count: int,
                   policy: str = 'both',
                   time_regex: str = r'(\d{14})',
                   time_fmt: str = '%Y%m%d%H%M%S', ext: str = '.tar.gz'):
    """清理云端旧备份,文件名时间戳统一为新格式 YYYYMMDDHHMMSS(14位数字)。

    policy 清理策略:
      count - 保留最新 N 份,其余全删,不看时间(固定份数)
      days  - 超过 N 天直接删,不看总数(定时清过期)
      both  - 超出 N 份 且 超过 N 天才删(默认,最稳妥)
      or    - 超出 N 份 或 超过 N 天就删(严格控存储上限,易误删近期备份,慎用)
    """
    policy_desc = {
        'count': f'保留最新 {retention_count} 份，其余全部删除，不看时间',
        'days': f'文件超过 {retention_days} 天直接删除，不看总数',
        'both': f'文件超过 {retention_days}天 并且 备份总数超过 {retention_count}份，才删除',
        'or': f'文件超过 {retention_days}天 或者 备份总数超过 {retention_count}份，就删除',
    }
    if policy not in policy_desc:
        raise ValueError(f'未知清理策略: {policy}，可选 count/days/both/or')
    log(f'清理策略[{policy}]：{policy_desc[policy]}')
    try:
        items = client.ls("/", detail=True)
    except Exception as e:
        log(f'列目录失败，跳过清理：{str(e)}')
        return

    backup_list = []
    for item in items:
        fname = item["name"]
        if not fname.endswith(ext):
            continue
        m = re.search(time_regex, fname)
        if not m:
            continue
        try:
            ftime = datetime.strptime(''.join(m.groups()), time_fmt)
            backup_list.append((ftime, fname))
        except ValueError:
            continue

    # 新的在前
    backup_list.sort(key=lambda x: x[0], reverse=True)
    log(f'云端现有备份总数: {len(backup_list)}')

    cutoff = datetime.now() - timedelta(days=retention_days)
    to_delete = []
    for idx, (ftime, fname) in enumerate(backup_list):
        over_count = idx >= retention_count
        expired = ftime < cutoff
        if (policy == 'count' and over_count) \
                or (policy == 'days' and expired) \
                or (policy == 'both' and over_count and expired) \
                or (policy == 'or' and (over_count or expired)):
            to_delete.append((ftime, fname))

    for ftime, fname in to_delete:
        log(f'删除旧备份: {fname}')
        try:
            client.remove(f"/{fname}")
        except Exception as e:
            log(f'删除失败 {fname}: {str(e)}')

    if not to_delete:
        log('无需删除，不满足【数量超限+时间过期】双条件')
