<div align="center">

<img src="docs/logo.svg" alt="ql-scripts" width="120">

<!-- 占位 Logo，替换为项目真实 Logo：docs/logo.png -->

# ql-scripts

**青龙面板自用脚本集：数据备份到 WebDAV + 多渠道任务通知**

![Python](https://img.shields.io/badge/Python-3.x-3776AB)
![Platform](https://img.shields.io/badge/Platform-青龙面板%20%2F%20Docker-2EA043)
![Dependencies](https://img.shields.io/badge/deps-webdav4%20·%20requests-blue)

[下载](https://github.com/lsx-xyg/ql-scripts/releases) · [反馈](https://github.com/lsx-xyg/ql-scripts/issues)

</div>

## 📚 目录

- [💡 这是什么](#-这是什么)
- [✨ 功能](#-功能)
- [🚀 安装](#-安装)
- [📖 使用](#-使用)
- [⚙️ 配置](#-配置)
- [🧩 扩展](#-扩展)
- [📁 项目结构](#-项目结构)

---

## 💡 这是什么

ql-scripts 是一套跑在[青龙面板](https://github.com/whyour/qinglong)上的 Python 自用脚本，目前包含青龙数据备份、RustDesk 备份和通用通知三个模块。

它解决两个问题：面板数据自动备份到 WebDAV 并按策略清理；任务执行结果通过可插拔的渠道（企微机器人、邮件）推送出去。

所有脚本共用 `common.py` 工具库（日志、文件名、环境变量、WebDAV 封装），通知渠道通过注册表扩展，加新平台不用改调用方。

## ✨ 功能

| 功能 | 说明 |
| :--- | :--- |
| 🗄️ 青龙备份 | 按别名打包 db、config、scripts 等目录 → 上传 WebDAV → 按数量/天数双策略清理云端旧备份 |
| 🖥️ RustDesk 备份 | 打包 RustDesk 数据与编排文件（自动过滤日志）→ 上传 → 清理旧备份 |
| 📣 多渠道通知 | 统一 `send()` 入口，内置企业微信机器人与 SMTP 邮件，失败自动指数退避重试 |
| 🧰 公共工具库 | 日志输出、文件名生成、环境变量读取、WebDAV 上传/清理的通用封装 |

## 🚀 安装

### 下载即用

在青龙面板「订阅管理」添加：

```bash
ql repo https://github.com/lsx-xyg/ql-scripts.git
```

订阅后在「依赖管理」安装 [requirements.txt](requirements.txt) 声明的依赖（`webdav4`、`requests`）。

### 从源码安装

```bash
git clone https://github.com/lsx-xyg/ql-scripts.git
cd ql-scripts
pip3 install -r requirements.txt
```

## 📖 使用

1. 在青龙「环境变量」里配置 WebDAV 与通知渠道所需变量（见下节）。
2. 给备份脚本设置定时（默认建议 `30 3 * * *`），手动运行一次验证上传与清理。
3. 通知脚本无需定时，在任意脚本结尾调用或用命令行测试：

```bash
# 命令行推送（默认走 NOTIFY_CHANNEL 指定渠道）
python3 notify.py -T "备份完成" "共 3 个文件"

# 指定渠道
python3 notify.py -c mail -T "备份完成" "详见日志"

# 在其他脚本里调用
from notify import send
send('任务通知', '**备份完成**\n> 共 3 个文件', channel='qywx')
```

## ⚙️ 配置

全部通过青龙「环境变量」配置，均有默认值或缺失时报错提示。常用项：

| 变量 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `WEBDAV_BASE_URL` | WebDAV 服务地址（备份脚本必需） | 无 |
| `WEBDAV_USER` / `WEBDAV_PASS` | WebDAV 账号密码 | 无 |
| `QL_BACKUP_INCLUDE` | 青龙备份目录别名，逗号分隔 | 无 |
| `RETENTION_DAYS` / `RETENTION_COUNT` | 云端备份保留天数 / 份数 | 7 / 7 |
| `CLEANUP_POLICY` | 清理策略：count / days / both / or | both |

<details>
<summary>全部环境变量</summary>

| 变量 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `QL_DATA_DIR` | 青龙数据目录 | /ql/data |
| `QL_HOST_DIR` | 宿主机目录（compose 备份用） | 无 |
| `RUSTDESK_DIR` | RustDesk 数据目录 | /source/rustdesk |
| `UPLOAD_RETRY` / `UPLOAD_RETRY_DELAY` | 上传重试次数 / 退避基础秒数 | 3 / 3 |
| `NOTIFY_CHANNEL` | 默认通知渠道 | qywx |
| `NOTIFY_RETRY` / `NOTIFY_RETRY_DELAY` | 通知重试次数 / 退避基础秒数 | 3 / 3 |
| `QYWX_WEBHOOK` | 企微群机器人 webhook（完整地址或仅 key） | 无 |
| `MAIL_HOST` / `MAIL_PORT` | SMTP 服务器 / 端口 | 无 / 465 |
| `MAIL_SSL` / `MAIL_STARTTLS` | SSL / STARTTLS 开关 | 465 时 SSL / false |
| `MAIL_USER` / `MAIL_PASS` | SMTP 账号 / 密码或授权码 | 无 |
| `MAIL_FROM` / `MAIL_TO` | 发件人 / 收件人（逗号分隔） | 取 MAIL_USER / 无 |

</details>

> [!NOTE]
> `QL_BACKUP_INCLUDE` 支持别名（base、config、scripts、deps、repo、ssh.d、dep_cache、log 等），完整映射见 [qinglong-backup.py](qinglong-backup.py) 文件头注释。

## 🧩 扩展

通知渠道按注册表分发，新增平台只需一个函数加装饰器，调用方无需改动（文件末尾附有钉钉骨架示例）：

```python
@register('dingtalk', '钉钉群机器人', ['DINGTALK_WEBHOOK'])
def send_dingtalk(title, content, msg_type='markdown'):
    ok, _ = _post_json(env('DINGTALK_WEBHOOK'), body, lambda d: d.get('errcode') == 0)
    return ok
```

## 📁 项目结构

```text
ql-scripts/
├── common.py            # 公共库：日志 / 文件名 / 环境变量 / WebDAV
├── notify.py            # 通用通知：qywx + mail 渠道，可注册扩展
├── qinglong-backup.py   # 青龙数据备份
├── rustdesk-backup.py   # RustDesk 备份
└── requirements.txt     # Python 依赖清单
```
