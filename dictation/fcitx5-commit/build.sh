#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> 检查编译依赖..."
MISSING_PKGS=()
for pkg in cmake extra-cmake-modules fcitx5; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if ! pacman -Qi base-devel &>/dev/null && ! command -v make &>/dev/null; then
    MISSING_PKGS+=("base-devel")
fi

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  缺少以下系统编译依赖: ${MISSING_PKGS[*]}"
    echo "请在终端手动运行以下命令安装，安装后重新执行本脚本："
    echo ""
    echo "  sudo pacman -S --needed ${MISSING_PKGS[*]}"
    echo ""
    exit 1
fi

echo "==> 编译 fcitx5-commit 插件 (纯普通用户权限)..."
cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build -j"$(nproc)"

echo ""
echo "=========================================================="
echo "✓ 编译成功！"
echo "由于安装到系统目录 (/usr/lib/fcitx5/) 需要 root 权限，"
echo "请手动执行以下命令完成安装并重启 Fcitx5："
echo ""
echo "  sudo cmake --install build && fcitx5 -r -d"
echo ""
echo "安装后可测试连通性："
echo "  busctl --user call org.fcitx.Fcitx5 /commit io.github.vendetta1871.Commit1 CommitString s \"直出测试✓\""
echo "=========================================================="
