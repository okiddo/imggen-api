# ImgGen API

简体中文 | [English](README.md)

ImgGen API 让 Codex 通过用户配置的 OpenAI-compatible Images API 生成或编辑图片。它会把结果直接保存为本地文件，并在 Codex 会话中展示，不依赖聊天记录图片恢复。

## 功能

- 生成、编辑或批量生成位图图片。
- 支持任何提供 OpenAI-compatible Images API 的兼容网关。
- 从环境变量或当前 Codex Provider 读取 API 地址和 Bearer 凭据。
- 将结果保存到明确的本地路径，方便稳定展示和后续使用。
- 在不产生付费生图请求的情况下检查连接和认证。
- 使用 `--dry-run` 预览请求内容。

## 使用条件

- 安装了内置 `imagegen` Skill 的 Codex 桌面版或 Codex CLI。
- Python 3.8 或更高版本。
- 支持 OpenAI-compatible 图片接口和 Bearer Key 认证的 API 服务商。

网关需要提供 `/v1/images/generations`。编辑图片还需要 `/v1/images/edits`。可选的 `doctor` 检查会访问 `/v1/models`。

## 在 Codex 中安装

在 Codex 中发送下面的安装请求：

```text
$skill-installer 请从 https://github.com/ChengLone/imggen-api/tree/main/skills/imggen-api 安装 imggen-api Skill
```

安装完成后新建一个 Codex 会话。如果没有立即显示该 Skill，请重启 Codex。

## 配置 API 服务商

在本机环境变量中设置 API 地址和 Bearer Key。不要把 API Key 粘贴到聊天中。

PowerShell：

```powershell
$env:IMAGEGEN_BASE_URL = "https://gateway.example.com/v1"
$env:IMAGEGEN_API_KEY = "your-api-key"
```

Bash：

```bash
export IMAGEGEN_BASE_URL="https://gateway.example.com/v1"
export IMAGEGEN_API_KEY="your-api-key"
```

如果当前启用的 Codex Provider 已配置兼容的 `base_url`，可以不设置 `IMAGEGEN_BASE_URL`。Skill 也可以读取该 Provider 配置的 `env_key`；当匹配的 Provider 使用 `requires_openai_auth = true` 时，还可以使用 Codex 的 API Key 缓存。

## 在 Codex 中使用

生成图片：

```text
$imggen-api 生成一张写实的狸花猫图片，清晨坐在窗边。
```

指定参数生成：

```text
$imggen-api 使用 gpt-image-2 生成一张 1536x1024 的 PNG 商品图，质量为 medium，并保存到 output/imagegen/。
```

编辑本地图片：

```text
$imggen-api 编辑 D:\Images\source.png：把背景替换成纯白摄影棚背景，保持主体不变。
```

Codex 会调用已配置的 API，验证输出文件，将图片保存到本地并在会话中展示。

## 诊断

在安装后的 Skill 目录中运行：

```powershell
python scripts/imggen_api.py doctor
```

该命令会检查 API 地址、Bearer 认证和网关公布的模型，不会生成图片。

使用下面的命令可以预览生图请求，而不调用图片接口：

```powershell
python scripts/imggen_api.py generate --model gpt-image-2 --prompt "test" --size 1024x1024 --quality medium --output-format png --out "D:\output\test.png" --dry-run
```

## 兼容范围

当前版本支持采用 OpenAI-compatible Images API，并通过 `Authorization: Bearer <key>` 认证的网关。需要 `X-API-Key`、命令生成令牌、自定义请求签名或专有图片接口的网关，需要单独适配。

## 更新

重新执行安装请求即可替换旧的独立安装副本。版本变化记录在 [CHANGELOG.md](CHANGELOG.md) 中。

