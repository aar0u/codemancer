"""Native mouse highlighter: ctypes on Windows, PyObjC on macOS."""

import argparse
import platform
import sys

COLORS = {
    "blue": ((100, 181, 246), (30, 136, 229)),
    "yellow": ((255, 223, 100), (255, 193, 7)),
    "green": ((129, 199, 132), (56, 142, 60)),
    "purple": ((179, 157, 219), (123, 31, 162)),
    "pink": ((244, 143, 177), (194, 24, 91)),
    "orange": ((255, 183, 77), (239, 108, 0)),
}


def run_windows(theme):
    import ctypes
    from ctypes import wintypes

    if not hasattr(wintypes, "HCURSOR"):
        wintypes.HCURSOR = wintypes.HANDLE
    if not hasattr(wintypes, "LRESULT"):
        wintypes.LRESULT = ctypes.c_ssize_t

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    WS_POPUP = 0x80000000
    WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x8, 0x8000000
    HWND_TOPMOST = wintypes.HWND(-1)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0002, 0x0010, 0x0200
    LWA_COLORKEY, LWA_ALPHA, BLACK, WM_PAINT, WM_TIMER, WM_DESTROY, WM_COMMAND = 1, 2, 0, 0x000F, 0x0113, 0x0002, 0x0111
    WM_TRAY, WM_RBUTTONUP, WM_LBUTTONUP = 0x8001, 0x0205, 0x0202
    NIM_ADD, NIM_DELETE, NIF_MESSAGE, NIF_ICON, NIF_TIP = 0, 2, 1, 2, 4
    MF_STRING, MF_SEPARATOR, MF_CHECKED, TPM_RIGHTBUTTON = 0, 0x800, 0x8, 0x2
    MENU_QUIT, MENU_THEME_BASE = 1, 100
    WH_MOUSE_LL, WM_MOUSEMOVE = 14, 0x0200
    BUTTON_MESSAGES = {0x0201: True, 0x0204: True, 0x0207: True, 0x0202: False, 0x0205: False, 0x0208: False}
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
    HIGHLIGHT_RADIUS, HIGHLIGHT_ALPHA, FRAME_MS, RAISE_EVERY = 25, 180, 16, 8

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL), ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

    class WNDCLASSEX(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HCURSOR), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", ctypes.c_wchar * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", ctypes.c_wchar * 256), ("uTimeoutOrVersion", wintypes.UINT), ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]

    WNDPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = wintypes.LRESULT
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.CreateIcon.argtypes = [wintypes.HINSTANCE, ctypes.c_int, ctypes.c_int, ctypes.c_byte, ctypes.c_byte, ctypes.c_void_p, ctypes.c_void_p]
    user32.CreateIcon.restype = wintypes.HICON
    user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = wintypes.LRESULT
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    state = {"pressed": False, "point": POINT(), "ticks": 0, "theme": theme}
    themes = tuple(COLORS)

    def cursor_rect(point):
        radius = HIGHLIGHT_RADIUS + 2
        return wintypes.RECT(point.x - x - radius, point.y - y - radius, point.x - x + radius, point.y - y + radius)

    def invalidate_cursor(hwnd):
        rect = cursor_rect(state["point"])
        user32.InvalidateRect(hwnd, ctypes.byref(rect), False)

    def create_tray_icon():
        size, radius = 16, 6
        outer = COLORS[state["theme"]][0]
        xor = bytearray(size * size * 4)
        for py in range(size):
            for px in range(size):
                offset = (py * size + px) * 4
                if (px - 7.5) ** 2 + (py - 7.5) ** 2 <= radius ** 2:
                    xor[offset:offset + 4] = bytes((outer[2], outer[1], outer[0], 255))
        and_mask = (ctypes.c_ubyte * (size * size // 8))()
        xor_mask = (ctypes.c_ubyte * len(xor)).from_buffer_copy(xor)
        return user32.CreateIcon(instance, size, size, 1, 32, and_mask, xor_mask)

    def paint(hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            clear = gdi32.CreateSolidBrush(BLACK)
            user32.FillRect(hdc, ctypes.byref(ps.rcPaint), clear)
            gdi32.DeleteObject(clear)
            point = state["point"]
            cursor_x, cursor_y = point.x - x, point.y - y
            outer, inner = COLORS[state["theme"]]
            def circle(radius, color):
                brush = gdi32.CreateSolidBrush(color[2] << 16 | color[1] << 8 | color[0])
                previous = gdi32.SelectObject(hdc, brush)
                gdi32.Ellipse(hdc, cursor_x - radius, cursor_y - radius, cursor_x + radius, cursor_y + radius)
                gdi32.SelectObject(hdc, previous)
                gdi32.DeleteObject(brush)
            circle(HIGHLIGHT_RADIUS, outer)
            if state["pressed"]:
                circle(17, inner)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    def show_menu(hwnd):
        menu = user32.CreatePopupMenu()
        for index, name in enumerate(themes):
            flags = MF_STRING | (MF_CHECKED if name == state["theme"] else 0)
            user32.AppendMenuW(menu, flags, MENU_THEME_BASE + index, name.capitalize())
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, MENU_QUIT, "Quit")
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(hwnd)
        user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON, point.x, point.y, 0, hwnd, None)
        user32.DestroyMenu(menu)

    @WNDPROC
    def window_proc(hwnd, message, wparam, lparam):
        if message == WM_TRAY and lparam in (WM_RBUTTONUP, WM_LBUTTONUP):
            show_menu(hwnd)
            return 0
        if message == WM_COMMAND:
            command = wparam & 0xFFFF
            if command == MENU_QUIT:
                user32.DestroyWindow(hwnd)
            elif MENU_THEME_BASE <= command < MENU_THEME_BASE + len(themes):
                state["theme"] = themes[command - MENU_THEME_BASE]
                invalidate_cursor(hwnd)
            return 0
        if message == WM_PAINT:
            paint(hwnd)
            return 0
        if message == WM_TIMER:
            old_rect = cursor_rect(state["point"])
            user32.GetCursorPos(ctypes.byref(state["point"]))
            user32.InvalidateRect(hwnd, ctypes.byref(old_rect), False)
            invalidate_cursor(hwnd)
            state["ticks"] = (state["ticks"] + 1) % RAISE_EVERY
            if not state["ticks"]:
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
            return 0
        if message == WM_DESTROY:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(tray))
            user32.DestroyIcon(tray_icon)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    @HOOKPROC
    def mouse_hook(code, message, data):
        if code >= 0 and message in BUTTON_MESSAGES:
            state["pressed"] = BUTTON_MESSAGES[message]
        return user32.CallNextHookEx(None, code, message, data)

    instance = kernel32.GetModuleHandleW(None)
    class_name = "MouseHighlightNative"
    window_class = WNDCLASSEX(ctypes.sizeof(WNDCLASSEX), 0, ctypes.cast(window_proc, ctypes.c_void_p), 0, 0, instance, None, None, None, None, class_name, None)
    if not user32.RegisterClassExW(ctypes.byref(window_class)):
        raise ctypes.WinError(ctypes.get_last_error())
    x, y = user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width, height = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    hwnd = user32.CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE, class_name, None, WS_POPUP, x, y, width, height, None, None, instance, None)
    user32.GetCursorPos(ctypes.byref(state["point"]))
    user32.SetLayeredWindowAttributes(hwnd, BLACK, HIGHLIGHT_ALPHA, LWA_COLORKEY | LWA_ALPHA)
    tray_icon = create_tray_icon()
    tray = NOTIFYICONDATA()
    tray.cbSize = ctypes.sizeof(tray)
    tray.hWnd, tray.uID = hwnd, 1
    tray.uFlags, tray.uCallbackMessage = NIF_MESSAGE | NIF_ICON | NIF_TIP, WM_TRAY
    tray.hIcon, tray.szTip = tray_icon, "Mouse Highlighter"
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(tray))
    user32.ShowWindow(hwnd, 8)  # SW_SHOWNA
    user32.SetTimer(hwnd, 1, FRAME_MS, None)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_hook, instance, 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    user32.UnhookWindowsHookEx(hook)


def run_macos(theme):
    try:
        from AppKit import (NSApp, NSApplication, NSApplicationActivationPolicyAccessory,
                            NSBackingStoreBuffered, NSBezierPath, NSColor, NSEvent, NSMenu,
                            NSMenuItem, NSPanel, NSScreen, NSStatusBar,
                            NSVariableStatusItemLength, NSView, NSWindowCollectionBehaviorCanJoinAllSpaces,
                            NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowCollectionBehaviorStationary,
                            NSWindowStyleMaskBorderless, NSEventMaskLeftMouseDown,
                            NSEventMaskLeftMouseUp, NSEventMaskRightMouseDown,
                            NSEventMaskRightMouseUp, NSEventTypeLeftMouseDown,
                            NSEventTypeRightMouseDown)
        from Foundation import NSObject, NSMakePoint, NSMakeRect, NSTimer
        from Quartz import CGWindowLevelForKey, kCGScreenSaverWindowLevelKey
    except ImportError as error:
        raise SystemExit("macOS requires: python -m pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz") from error

    state = {"pressed": False, "point": NSMakePoint(0, 0), "theme": theme}

    class HighlightView(NSView):
        def initWithFrame_origin_(self, frame, origin):
            self = self.initWithFrame_(frame)
            self.origin = origin
            return self

        def drawRect_(self, _rect):
            outer, inner = COLORS[state["theme"]]
            point = NSMakePoint(state["point"].x - self.origin.x, state["point"].y - self.origin.y)
            for radius, color in ((25, outer), (17, inner) if state["pressed"] else (0, None)):
                if radius:
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(color[0] / 255, color[1] / 255, color[2] / 255, 0.7 if radius == 25 else 0.86).set()
                    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(point.x - radius, point.y - radius, radius * 2, radius * 2)).fill()

    class AppDelegate(NSObject):
        def tick_(self, _timer):
            state["point"] = NSEvent.mouseLocation()
            for panel in self.panels:
                panel.contentView().setNeedsDisplay_(True)

        def theme_(self, sender):
            state["theme"] = sender.representedObject()
            for name, item in self.theme_items.items():
                item.setState_(name == state["theme"])

        def quit_(self, _sender):
            NSApp.terminate_(None)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    frames = [screen.frame() for screen in NSScreen.screens()]
    left, bottom = min(frame.origin.x for frame in frames), min(frame.origin.y for frame in frames)
    right, top = max(frame.origin.x + frame.size.width for frame in frames), max(frame.origin.y + frame.size.height for frame in frames)
    desktop = NSMakeRect(left, bottom, right - left, top - bottom)
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(desktop, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(False)
    panel.setHidesOnDeactivate_(False)
    panel.setIgnoresMouseEvents_(True)
    panel.setLevel_(CGWindowLevelForKey(kCGScreenSaverWindowLevelKey))
    panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary | NSWindowCollectionBehaviorStationary)
    panel.setContentView_(HighlightView.alloc().initWithFrame_origin_(NSMakeRect(0, 0, desktop.size.width, desktop.size.height), desktop.origin))
    panel.orderFrontRegardless()
    delegate.panels = [panel]

    menu = NSMenu.alloc().init()
    delegate.theme_items = {}
    for name in COLORS:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(name.capitalize(), "theme:", "")
        item.setTarget_(delegate)
        item.setRepresentedObject_(name)
        item.setState_(name == state["theme"])
        menu.addItem_(item)
        delegate.theme_items[name] = item
    menu.addItem_(NSMenuItem.separatorItem())
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Mouse Highlighter", "quit:", "q")
    item.setTarget_(delegate)
    menu.addItem_(item)
    status = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    status.button().setTitle_("●")
    status.setMenu_(menu)

    def on_mouse(event):
        state["pressed"] = event.type() in (NSEventTypeLeftMouseDown, NSEventTypeRightMouseDown)
    delegate.monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
        NSEventMaskLeftMouseDown | NSEventMaskLeftMouseUp | NSEventMaskRightMouseDown | NSEventMaskRightMouseUp,
        on_mouse,
    )
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1 / 60, delegate, "tick:", None, True)
    app.run()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", choices=COLORS, default="yellow")
    args = parser.parse_args()
    system = platform.system()
    if system == "Windows":
        run_windows(args.theme)
    elif system == "Darwin":
        run_macos(args.theme)
    else:
        raise SystemExit(f"Unsupported platform: {system}")


if __name__ == "__main__":
    main()
