# Dictation (SenseVoice-Small + sherpa-onnx)

本地离线的 Push-to-Talk 语音输入，适用于 Linux (CachyOS + KDE Plasma / Wayland)。
按住键盘按键（默认 Keychron C1 麦克风键 / `KEY_RIGHTALT`）或鼠标侧键（`BTN_EXTRA`）说话，松开即打字上屏。

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

默认监听所有支持 `KEY_RIGHTALT`（键盘）和 `BTN_EXTRA`（鼠标侧键）的物理设备。如果需要指定设备或修改按键，跑之前设环境变量就行（自定义按键码可用 `./sniff_key.py` 探测）：

```bash
DICTATE_KEYBOARD_KEY=KEY_RIGHTALT DICTATE_MOUSE_BUTTON=BTN_EXTRA ./dictate.py

# 限制仅监听特定物理路径（默认留空自动监听全部匹配设备）
DICTATE_KEYBOARD_DEVICE=/dev/input/by-id/xxx-event-kbd ./dictate.py
```

如需在桌面环境绑定点击切换（Toggle 模式），先用 `./dictate.py --toggle` 启动，快捷键设置里执行 `python3 /path/to/dictation/toggle.py` 即可。

## 关键技术选型依据

### 1. 为什么用整段解码，不用 VAD 分段
Push-to-Talk 按键本身就是最精准的语音起止边界。早期尝试过 Silero VAD 停顿切分，但切片拼缝逻辑复杂且易吞字；改用整句直送 SenseVoice（原生支持 30s 长句）后识别更准、延迟更低。

### 2. 为什么不加本地 LLM 纠错层
实测过使用 Qwen2.5-0.5B 与 1.5B 做文本后处理纠错：
- **0.5B** 无法严格遵循最小编辑原则，倾向过度改写、篡改术语甚至造谣；
- **1.5B** 纠错能力虽有提升，但出现新的恶性缺陷——极易将中英混说整句误翻成纯英文；
- CPU 延迟由 70ms 激增至 0.8~1.6s，彻底破坏听写“即说即出”的流畅度。因此维持纯 ASR 直出。

### 3. 为什么用剪贴板 + Shift+Insert 注入
`ydotool key` 模拟真实的内核级 Shift+Insert 按键，避开 Wayland 合成器协议限制与按键映射表，对终端（如 Konsole）和 GUI 软件兼容性极佳，注入后自动恢复原始剪贴板内容。
