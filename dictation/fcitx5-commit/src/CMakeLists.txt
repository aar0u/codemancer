add_fcitx5_addon(commit commit.cpp)
target_link_libraries(commit PRIVATE Fcitx5::Core Fcitx5::Module::DBus)

configure_file(commit.conf.in "${CMAKE_CURRENT_BINARY_DIR}/commit.conf" @ONLY)

install(TARGETS commit DESTINATION "${FCITX_INSTALL_ADDONDIR}")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/commit.conf"
        DESTINATION "${FCITX_INSTALL_PKGDATADIR}/addon")
