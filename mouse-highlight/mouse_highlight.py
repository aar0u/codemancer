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


def run_windows(colors):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WS_POPUP = 0x80000000
    WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x8, 0x8000000
    LWA_COLORKEY, BLACK, WM_PAINT, WM_TIMER, WM_DESTROY = 1, 0, 0x000F, 0x0113, 0x0002
    WH_MOUSE_LL, WM_MOUSEMOVE = 14, 0x0200
    BUTTON_MESSAGES = {0x0201: True, 0x0204: True, 0x0207: True, 0x0202: False, 0x0205: False, 0x0208: False}
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL), ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

    class WNDCLASSEX(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HCURSOR), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    WNDPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    state = {"pressed": False, "point": POINT()}

    def paint(hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            user32.GetCursorPos(ctypes.byref(state["point"]))
            point = state["point"]
            cursor_x, cursor_y = point.x - x, point.y - y
            outer, inner = colors
            def circle(radius, color):
                brush = gdi32.CreateSolidBrush(color[2] << 16 | color[1] << 8 | color[0])
                gdi32.SelectObject(hdc, brush)
                gdi32.Ellipse(hdc, cursor_x - radius, cursor_y - radius, cursor_x + radius, cursor_y + radius)
                gdi32.DeleteObject(brush)
            circle(25, outer)
            if state["pressed"]:
                circle(17, inner)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    @WNDPROC
    def window_proc(hwnd, message, wparam, lparam):
        if message == WM_PAINT:
            paint(hwnd)
            return 0
        if message == WM_TIMER:
            user32.InvalidateRect(hwnd, None, True)
            return 0
        if message == WM_DESTROY:
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
    user32.SetLayeredWindowAttributes(hwnd, BLACK, 0, LWA_COLORKEY)
    user32.ShowWindow(hwnd, 8)  # SW_SHOWNA
    user32.SetTimer(hwnd, 1, 16, None)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_hook, instance, 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    user32.UnhookWindowsHookEx(hook)


def run_macos(colors):
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

    state = {"pressed": False, "point": NSMakePoint(0, 0)}

    class HighlightView(NSView):
        def initWithFrame_origin_(self, frame, origin):
            self = self.initWithFrame_(frame)
            self.origin = origin
            return self

        def drawRect_(self, _rect):
            outer, inner = colors
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
        run_windows(COLORS[args.theme])
    elif system == "Darwin":
        run_macos(COLORS[args.theme])
    else:
        raise SystemExit(f"Unsupported platform: {system}")


if __name__ == "__main__":
    main()
