# Dictation (SenseVoice-Small + sherpa-onnx)

本地离线的 Push-to-Talk 语音输入，适用于 Linux (CachyOS + Hyprland / Wayland)。
按住快捷键（右 Ctrl 或鼠标侧键）说话，松开即打字上屏。快捷键由 Hyprland 的 bind 触发，守护进程不读 `/dev/input`，也不写 `/dev/uinput`，用户不需要加入 `input` 组。

## 架构

- `dictate.py` —— 核心脚本。首次运行自动下载 SenseVoice-Small int8 ONNX 模型（到 `$SENSEVOICE_MODEL_DIR`，默认 `~/.local/share/sensevoice`）；监听 `$XDG_RUNTIME_DIR/dictate.sock`（权限 600），接收 `start <source>`、`stop <source>`、`toggle`；松开后整段音频一次性送入解码（CPU 推理仅 ~75ms）；文字优先走 fcitx5 D-Bus 提交，回退到 `wl-copy` + `wtype` (Shift+Insert)。
- `toggle.py` —— 纯 stdlib 的轻量客户端，向 socket 发送上述指令，由 Hyprland bind 调用。

## 快捷键（`hypr/hyprland.lua`）

按下发 `start`，松开发 `stop`。`source` 区分来源，只有启动录音的来源才能停止它。`non_consuming` 让右 Ctrl 仍可正常用作 Ctrl；右 Ctrl 的松开事件需要 `ignore_mods`，否则不触发。

```lua
local dictate = "python3 /mnt/storage/dev/codemancer/dictation/toggle.py"
hl.bind("Control_R", hl.dsp.exec_cmd(dictate .. " start kbd"),  { non_consuming = true })
hl.bind("Control_R", hl.dsp.exec_cmd(dictate .. " stop kbd"),   { non_consuming = true, release = true, ignore_mods = true })
hl.bind("mouse:276", hl.dsp.exec_cmd(dictate .. " start mouse"), { non_consuming = true })  -- BTN_EXTRA
hl.bind("mouse:276", hl.dsp.exec_cmd(dictate .. " stop mouse"),  { non_consuming = true, release = true })
```

## 使用方式

### 方式一：Ad-hoc 独立运行（前台调试 / 免安装）

直接在终端前台启动，实时打印录音、推理耗时与文字结果，`Ctrl+C` 随时退出：

```bash
# 1. 基础本地离线运行（初次运行自动拉取模型并就绪）
./dictate.py
# 或使用 uv：
uv run dictate.py

# 2. 临时搭配云端 API 测试
DICTATE_API_KEY="gsk_xxxxxxxxxxxx" uv run dictate.py

# 3. 另开终端手动触发一次录音/停止
python3 toggle.py
```

---

### 方式二：常驻后台（Systemd 用户服务）

适合日常长期使用，开机随桌面环境自启：

```bash
# 一键安装依赖并注册启动 systemd 服务
bash install.sh

# 查看实时运行日志
journalctl --user -u dictate -f

# 重启服务
systemctl --user restart dictate

# 完全卸载（清理模型、移除 service）
bash uninstall.sh
```

长期常驻使用时，推荐直接写入用户配置环境文件 `~/.config/dictate/env`（权限已锁 600，不进 git 仓库，安全省心）：

```bash
mkdir -p ~/.config/dictate
cat > ~/.config/dictate/env << 'EOF'
DICTATE_API_KEY=gsk_xxxxxxxxxxxx
# 可选覆盖以下项（默认即为 Groq whisper-large-v3-turbo）：
# DICTATE_API_BASE=https://api.groq.com/openai/v1
# DICTATE_API_MODEL=whisper-large-v3-turbo
EOF
chmod 600 ~/.config/dictate/env
systemctl --user restart dictate
```

所有可用配置项及默认值：

```bash
# 云端 ASR API 配置（可选，标准 OpenAI 协议，配置 API Key 即自动启用）
DICTATE_API_KEY=gsk_xxxxxxxxxxxx                 # 或标准 OPENAI_API_KEY / GROQ_API_KEY
DICTATE_API_BASE=https://api.groq.com/openai/v1   # 默认 Groq；可换硅基流动、官方 OpenAI 或自建服务
DICTATE_API_MODEL=whisper-large-v3-turbo          # 默认模型
```

- **引擎工作模式**：
  - **云端模式**（配置了 API Key）：每次说话请求云端 GPU/LPU，~150ms 极速返回满血 Whisper 识别结果。**若网络故障或 API 报错，直接弹窗报错提示，不隐式回退**，确保异常被明确感知。
  - **离线模式**（未配置 API Key）：启动时自动加载本地 SenseVoice-Small int8 模型，断网也能 70ms 瞬出。
- **文字注入自适应**：优先走 `fcitx5-commit` 原生 D-Bus 直出（零剪贴板污染）；若输入框无焦点或插件未就绪，自动回退到 `wl-copy` + `wtype` (Shift+Insert)。

## 关键技术选型依据

### 1. 为什么用整段解码，不用 VAD 分段
Push-to-Talk 按键本身就是最精准的语音起止边界。早期尝试过 Silero VAD 停顿切分，但切片拼缝逻辑复杂且易吞字；改用整句直送 SenseVoice（原生支持 30s 长句）后识别更准、延迟更低。

### 2. 为什么不加本地 LLM 纠错层
实测过使用 Qwen2.5-0.5B 与 1.5B 做文本后处理纠错：
- **0.5B** 无法严格遵循最小编辑原则，倾向过度改写、篡改术语甚至造谣；
- **1.5B** 纠错能力虽有提升，但出现新的恶性缺陷——极易将中英混说整句误翻成纯英文；
- CPU 延迟由 70ms 激增至 0.8~1.6s，彻底破坏听写“即说即出”的流畅度。因此维持纯 ASR 直出。

### 3. 文字注入方式：Fcitx5 原生提交优先，剪贴板保底
- **Fcitx5 原生提交（推荐，彻底告别剪贴板）**：仓库内自带源码，执行 `./fcitx5-commit/build.sh` 即可一键编译安装到系统。`dictate.py` 会直接通过系统 D-Bus (`busctl`) 将文字交给 Fcitx5 的 `commitString` 在光标处微秒级原子上屏，完全不触碰系统剪贴板、零竞态。
- **剪贴板 + Shift+Insert（无感保底）**：若未检测到 Fcitx5 commit 接口，自动回退到 `wl-copy` + `wtype`（Wayland virtual-keyboard 协议）模拟 Shift+Insert，并在粘贴后自动还原剪贴板内容。不用 `ydotool`：它写 `/dev/uinput`，需要 `input` 组权限，而且沙箱里的程序拿到同样权限就能往系统里注入按键。
