cmake_minimum_required(VERSION 3.16)

project(fcitx5-commit VERSION 0.1.0 LANGUAGES CXX)

# Oldest fcitx5 whose headers and addon loader provide everything used here
# (FCITX_ADDON_FACTORY_V2, Instance::mostRecentInputContext, IDBusModule::bus).
set(REQUIRED_FCITX_VERSION 5.1.0)

find_package(Fcitx5Core ${REQUIRED_FCITX_VERSION} REQUIRED)
find_package(Fcitx5Module REQUIRED COMPONENTS DBus)

include(GNUInstallDirs)
# C++20, -Wall -Wextra, hidden visibility, --no-undefined: the same settings
# fcitx5 builds its own addons with.
include("${FCITX_INSTALL_CMAKECONFIG_DIR}/Fcitx5Utils/Fcitx5CompilerSettings.cmake")

add_subdirectory(src)
