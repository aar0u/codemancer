/*
 * SPDX-FileCopyrightText: 2026 Vendetta1871
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * fcitx5 addon that exposes one D-Bus method on fcitx5's own session-bus
 * connection (org.fcitx.Fcitx5):
 *
 *   object    /commit
 *   interface io.github.vendetta1871.Commit1
 *   method    CommitString(s text) -> (b committed)
 *
 * It commits `text` to the currently focused input context, the same way an
 * input method commits a selected candidate.
 */

#include <memory>
#include <string>

#include <fcitx-utils/dbus/bus.h>
#include <fcitx-utils/dbus/objectvtable.h>
#include <fcitx-utils/log.h>
#include <fcitx/addonfactory.h>
#include <fcitx/addoninstance.h>
#include <fcitx/addonmanager.h>
#include <fcitx/inputcontext.h>
#include <fcitx/instance.h>

#include "dbus_public.h"

namespace fcitx {

namespace {

FCITX_DEFINE_LOG_CATEGORY(commitLog, "commit");

#define COMMIT_DEBUG() FCITX_LOGC(commitLog, Debug)
#define COMMIT_ERROR() FCITX_LOGC(commitLog, Error)

constexpr char kObjectPath[] = "/commit";
constexpr char kInterface[] = "io.github.vendetta1871.Commit1";

} // namespace

class CommitModule;

// The D-Bus object. Kept separate from the addon so the addon owns its
// lifetime; destroying it unregisters /commit from the bus.
class CommitService : public dbus::ObjectVTable<CommitService> {
public:
    explicit CommitService(CommitModule *module) : module_(module) {}

    bool commitString(const std::string &text);

private:
    CommitModule *module_;

    FCITX_OBJECT_VTABLE_METHOD(commitString, "CommitString", "s", "b");
};

class CommitModule : public AddonInstance {
public:
    explicit CommitModule(Instance *instance);

    // Commits `text` to the focused input context. Returns false (and commits
    // nothing) when no input context has focus, so an empty string works as
    // a probe for "is there somewhere to type into".
    bool commitString(const std::string &text);

private:
    Instance *instance_;
    FCITX_ADDON_DEPENDENCY_LOADER(dbus, instance_->addonManager());
    std::unique_ptr<CommitService> service_;
};

CommitModule::CommitModule(Instance *instance) : instance_(instance) {
    AddonInstance *dbusAddon = dbus();
    dbus::Bus *bus = dbusAddon ? dbusAddon->call<IDBusModule::bus>() : nullptr;
    if (!bus) {
        COMMIT_ERROR() << "dbus addon is not available, " << kObjectPath
                       << " is not exported";
        return;
    }

    auto service = std::make_unique<CommitService>(this);
    if (!bus->addObjectVTable(kObjectPath, kInterface, *service)) {
        COMMIT_ERROR() << "failed to export " << kInterface << " at "
                       << kObjectPath;
        return;
    }
    service_ = std::move(service);
    COMMIT_DEBUG() << "exported " << kInterface << " at " << kObjectPath;
}

bool CommitModule::commitString(const std::string &text) {
    InputContext *ic = instance_->mostRecentInputContext();
    if (!ic || !ic->hasFocus()) {
        COMMIT_DEBUG() << "no focused input context, ignoring " << text.size()
                       << " byte(s)";
        return false;
    }
    if (!text.empty()) {
        COMMIT_DEBUG() << "committing " << text.size() << " byte(s) to "
                       << ic->program() << " via " << ic->frontendName();
        ic->commitString(text);
    }
    return true;
}

bool CommitService::commitString(const std::string &text) {
    return module_->commitString(text);
}

class CommitModuleFactory : public AddonFactory {
public:
    AddonInstance *create(AddonManager *manager) override {
        return new CommitModule(manager->instance());
    }
};

} // namespace fcitx

FCITX_ADDON_FACTORY_V2(commit, fcitx::CommitModuleFactory);
