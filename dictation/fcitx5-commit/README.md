# fcitx5-commit

- **Upstream Repository**: https://github.com/Vendetta1871/fcitx5-commit

Fcitx5 原生 C++ D-Bus 插件，允许外部程序向当前有焦点的输入框直接提交文本（调用 `ic->commitString`），不触碰系统剪贴板。

## 依赖 (Arch / CachyOS)

```bash
sudo pacman -S --needed cmake extra-cmake-modules fcitx5 base-devel
```

## 编译与安装

```bash
# 编译
./build.sh

# 安装并重启 Fcitx5
sudo cmake --install build && fcitx5 -r -d
```

## 测试

在任意输入框中聚焦，运行：

```bash
busctl --user call org.fcitx.Fcitx5 /commit io.github.vendetta1871.Commit1 CommitString s "直出测试✓"
```
