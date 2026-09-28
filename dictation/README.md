# Dictation (SenseVoice-Small + sherpa-onnx)

本地离线的 Push-to-Talk 语音输入，适用于 Linux (CachyOS + KDE Plasma / Wayland)。
按住键盘按键（默认 `KEY_RIGHTCTRL`，即右 Ctrl）或鼠标侧键（`BTN_EXTRA`）说话，松开即打字上屏。

## 架构

- `dictate.py` —— 核心脚本，adhoc 手动运行（前台跑，`Ctrl+C` 停）。首次运行自动下载 SenseVoice-Small int8 ONNX 模型（到 `$SENSEVOICE_MODEL_DIR`，默认 `~/.local/share/sensevoice`）；动态扫描并监听所有包含目标热键的物理输入设备（evdev 设备池，即插即用）；松开按键后整段音频一次性送入解码（CPU 推理仅 ~75ms）；通过 `wl-copy` + `ydotool` (Shift+Insert) 模拟按键注入焦点窗口。默认只用 evdev 热键，不开 socket；加 `--toggle` 才会监听 `$XDG_RUNTIME_DIR/dictate.sock`，用完随进程退出自动清理，不会留垃圾文件。
- `toggle.py` —— 纯 stdlib 的轻量客户端，向 `$XDG_RUNTIME_DIR/dictate.sock` 发送信号，给用 `--toggle` 启动的 `dictate.py` 做手动 toggle 触发。
- `sniff_key.py` —— 辅助脚本，用于探测新键盘或鼠标按键的 evdev 键码。

## 安装与使用

```bash
bash install.sh
./dictate.py
```

卸载（删除下载的模型；系统包和 `input` 组成员身份保留，脚本会打印可选命令）：

```bash
bash uninstall.sh
```

## 按键与设备配置

默认监听所有支持 `KEY_RIGHTCTRL`（键盘）和 `BTN_EXTRA`（鼠标侧键）的物理设备。如果需要指定设备或修改按键，跑之前设环境变量就行（自定义按键码可用 `./sniff_key.py` 探测）：

```bash
DICTATE_KEYBOARD_KEY=KEY_CAPSLOCK DICTATE_MOUSE_BUTTON=BTN_EXTRA ./dictate.py

# 限制仅监听特定物理路径（默认留空自动监听全部匹配设备）
DICTATE_KEYBOARD_DEVICE=/dev/input/by-id/xxx-event-kbd ./dictate.py
```

选键要避开任何应用/DE 会响应"单独按下再松开"这个动作的键：`dictate.py` 监听设备是非独占的（不做 `grab()`），按键会同时正常传给桌面环境。`KEY_RIGHTALT`（以及左 Alt）尤其不能用——GTK/Firefox 等工具包把"单独按下再松开 Alt、中间不按其他键"固定解释为"切换菜单栏显示"，这正好是 push-to-talk 的标准触发方式，结构性冲突，换哪个 Alt 都一样。换个没有这种全局单键语义的物理键（`KEY_RIGHTCTRL`、`KEY_PAUSE`、`KEY_SCROLLLOCK`、`KEY_CAPSLOCK` 之类，用 `./sniff_key.py` 探测键码）即可，不是代码 bug，也不需要靠独占 grab 来"抢"——独占会连累整个键盘所有按键都进不了系统。

如需在桌面环境绑定点击切换（Toggle 模式），先用 `./dictate.py --toggle` 启动，快捷键设置里执行 `python3 /path/to/dictation/toggle.py` 即可。

某些终端（如 WezTerm）的 Shift+Insert 走的是 PRIMARY selection（鼠标选中那份缓冲区），不是 CLIPBOARD（Ctrl+C/V 那份）——两块独立缓冲区，`type_text()` 两份都写、都恢复（`wl-copy --primary`）。如果某个终端读取剪贴板特别慢，赶不上粘贴后自动恢复旧内容的时机，可以调大延迟：`DICTATE_CLIPBOARD_RESTORE_DELAY=1.0 ./dictate.py`。

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
- **剪贴板 + Shift+Insert（无感保底）**：若未检测到 Fcitx5 commit 接口，自动回退到 `wl-copy` + `ydotool` 模拟内核 Shift+Insert，并在粘贴后自动还原剪贴板内容。
- 可通过环境变量强行指定方式：`DICTATE_INJECT_METHOD=fcitx` 或 `DICTATE_INJECT_METHOD=clipboard`（默认 `auto`）。
