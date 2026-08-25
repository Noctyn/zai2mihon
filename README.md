# zai2mihon

将再漫画（ZaiManhua / i.zaimanhua.com）的书架订阅和阅读历史导出为 Mihon / Tachiyomi 兼容的 `.tachibk` 备份文件。

## 功能特性

- **直接导出**：通过 JWT Token 导出书架订阅与阅读历史，生成标准 `.tachibk` 备份文件。
- **备份合并**：支持将云端数据合并至手机已导出的 `.tachibk` 文件中，精准更新已读章节与历史时间戳，不破坏原有书架与其它图源数据。
- **图源规范对齐**：完美适配 Mihon / Tachiyomi 再漫画图源扩展（Source ID: `524579092615598717`），漫画 URL 及章节路径与扩展完全一致。
- **自动重试与断线重连**：针对网络波动及长列表分页拉取内置自动重试与指数退避。
- **分类管理**：支持自定义书架分类、多分类标签映射或留空未分类。
- **离线转换**：支持将本地 JSON 格式的订阅数据转换为 `.tachibk`。
- **备份检查**：内置 `inspect` 命令查看 `.tachibk` 文件内容与漫画预览。

---

## 🔑 如何获取再漫画 Token

再漫画 API 使用 Bearer JWT Token 进行身份验证。获取步骤如下：

### 第一步：打开浏览器并登录
打开浏览器访问并登录再漫画官网（如 [i.zaimanhua.com](https://i.zaimanhua.com) 或 [www.zaimanhua.com](https://www.zaimanhua.com)）。

### 第二步：打开开发者工具抓包
1. 按 <kbd>F12</kbd>（或右键网页空白处选择 **检查 / Inspect**）打开开发者工具；
2. 切换到顶部的 **网络 (Network)** 标签页；
3. 在筛选搜索框中输入 `comic/sub/list` 或 `readingRecord/list`；
4. 点击网页上的 **我的订阅** 或 **阅读历史**，列表中会出现一条接口请求。

### 第三步：复制 Token
1. 点击该条请求，在右侧面板切换到 **标头 (Headers)** 选项卡；
2. 向下滚动找到 **请求标头 (Request Headers)** 中的 `authorization`；
3. 复制其后面的值（形如 `Bearer eyJhbGci...` 或直接复制 `eyJhbGci...` 这段 JWT 字符串即可）。

> **💡 提示**：
> - 工具会自动识别并去除 `Bearer ` 前缀与多余空格、引号。
> - 您也可以将 Token 设置到环境变量 `ZAIMANHUA_TOKEN` 中，无需每次在命令行重复输入。

---

## 快速使用

### 方式一：直接运行可执行程序（免安装 Python）
从 [Releases 页面](../../releases) 下载对应平台的单文件绿色程序（如 `zai2mihon-windows-amd64.exe`），双击即可启动交互式向导。

### 方式二：使用 uv / Python 运行
```bash
# 启动交互式引导向导
uv run zai2mihon
```

---

## 命令行使用

### 1. 合并到现有备份（推荐）

将云端数据注入手机导出的备份文件中：

```bash
uv run zai2mihon merge --token "<YOUR_TOKEN>" -b backup.tachibk -o merged.tachibk -c "再漫画"
```

### 2. 导出完整备份（订阅 + 历史）

```bash
uv run zai2mihon export --token "<YOUR_TOKEN>" -o backup.tachibk
```

### 3. 仅导出书架订阅（不含历史记录）

```bash
uv run zai2mihon export --token "<YOUR_TOKEN>" --no-include-history -o backup.tachibk
```

### 4. 仅导出阅读历史

```bash
uv run zai2mihon export --token "<YOUR_TOKEN>" --history-only -o backup.tachibk
```

### 5. 转换本地 JSON 文件

```bash
uv run zai2mihon convert input.json -o output.tachibk -c "再漫画"
```

### 6. 查看备份文件内容

```bash
uv run zai2mihon inspect backup.tachibk
```

---

## 参数说明

### `export` 参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `-t, --token` | 再漫画 Token（可省略，回退到环境变量 `ZAIMANHUA_TOKEN` 或掩码输入） | - |
| `-o, --output` | 输出文件路径 | `zaimanhua_backup_YYYY-MM-DD_HH-MM.tachibk` |
| `-b, --existing-backup` | 待合并的现有备份路径 | 无 |
| `-c, --category` | 书架分类名称（传入 `none` 禁用分类） | `再漫画` |
| `-u, --base-url, --url` | 再漫画 API 地址 | `https://i.zaimanhua.com` |
| `--no-include-history` | 不导出阅读历史 | `False` |
| `--history-only` | 仅导出阅读历史 | `False` |
| `-s, --source-id` | 图源 ID | `524579092615598717` |
| `--source-name` | 图源名称 | `再漫画` |
| `--proxy` | HTTP / SOCKS 代理地址 | 无 |
| `--no-export-json` | 不同时生成 JSON 文件 | `False` |
| `--debug` | 启用调试模式并输出完整错误堆栈 | `False` |

### `merge` 参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `-t, --token` | 再漫画 Token（可省略，回退到环境变量 `ZAIMANHUA_TOKEN` 或掩码输入） | - |
| `-b, --backup-file` | 现有的 `.tachibk` 文件路径（必填） | - |
| `-o, --output` | 输出文件路径 | `<原文件名>_merged.tachibk` |
| `-c, --category` | 分类名称（传入 `none` 禁用分类） | `再漫画` |
| `-u, --base-url, --url` | 再漫画 API 地址 | `https://i.zaimanhua.com` |
| `-s, --source-id` | 图源 ID | `524579092615598717` |
| `--source-name` | 图源名称 | `再漫画` |
| `--proxy` | HTTP / SOCKS 代理地址 | 无 |
| `--debug` | 启用调试模式并输出完整错误堆栈 | `False` |

### 环境变量

- `ZAIMANHUA_BASE_URL`：覆盖默认 API 基础地址（默认为 `https://i.zaimanhua.com`）。
- `ZAIMANHUA_TOKEN`：提供再漫画 Token，避免在命令行明文传入。
- `ZAIMANHUA_DEBUG`：设置为 `1` 时启用调试模式并输出完整错误堆栈（等同于 `--debug`）。

---

## 运行测试

```bash
uv run python -m pytest -v
```

## 打包为可执行文件 (.exe)

```bash
uv run python -m PyInstaller --onefile --name zai2mihon --clean main.py
```

打包完成后，可执行文件位于 `dist/zai2mihon.exe`，无需 Python 环境即可独立运行。

## License

MIT
