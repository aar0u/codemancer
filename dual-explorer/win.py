"""Windows-only OS integration via ctypes (no pywin32).

Includes OLE drag-out/in, clipboard file transfer (CF_HDROP), shell helpers,
and a directory watcher.
"""

import ctypes
import os
import subprocess
import threading
from ctypes import wintypes

ole32 = ctypes.oledll.ole32
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

HRESULT = ctypes.HRESULT


def _log(message):
    print(f"[win] {message}", flush=True)


# Shared COM/HGLOBAL/CF_HDROP bindings.

CF_HDROP = 15
TYMED_HGLOBAL = 1
GHND = 0x0002 | 0x0040  # GMEM_MOVEABLE | GMEM_ZEROINIT

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

S_OK = 0
S_FALSE = 1
E_NOTIMPL = -2147467263        # 0x80004001
E_NOINTERFACE = -2147467262    # 0x80004002
DV_E_FORMATETC = -2147221404   # 0x80040064

DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1
DROPEFFECT_MOVE = 2

DVASPECT_CONTENT = 1


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(GUID)]


def _guid(text):
    guid = GUID()
    ole32.CLSIDFromString(text, ctypes.byref(guid))
    return guid


def _guid_bytes(guid):
    return ctypes.string_at(ctypes.addressof(guid), ctypes.sizeof(guid))


IID_IUnknown = _guid("{00000000-0000-0000-C000-000000000046}")


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


class FORMATETC(ctypes.Structure):
    _fields_ = [
        ("cfFormat", ctypes.c_ushort),
        ("ptd", ctypes.c_void_p),
        ("dwAspect", ctypes.c_ulong),
        ("lindex", ctypes.c_long),
        ("tymed", ctypes.c_ulong),
    ]


class STGMEDIUM(ctypes.Structure):
    _fields_ = [
        ("tymed", ctypes.c_ulong),
        ("hGlobal", ctypes.c_void_p),
        ("pUnkForRelease", ctypes.c_void_p),
    ]


# COM vtable callback types.

QueryInterfaceFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
AddRefFn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
ReleaseFn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
QueryContinueDragFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD)
GiveFeedbackFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD)
GetDataFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM))
GetDataHereFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM))
QueryGetDataFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC))
GetCanonicalFormatEtcFn = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC), ctypes.POINTER(FORMATETC)
)
SetDataFn = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM), wintypes.BOOL
)
EnumFormatEtcFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))
DAdviseFn = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.POINTER(FORMATETC), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)
)
DUnadviseFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD)
EnumDAdviseFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
NextFn = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(FORMATETC), ctypes.POINTER(wintypes.ULONG)
)
SkipFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.ULONG)
ResetFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p)
CloneFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))


class _ComObject(ctypes.Structure):
    """A COM object's first member is a pointer to its vtable."""
    _fields_ = [("lpVtbl", ctypes.c_void_p)]


def _build_hdrop_handle(paths):

    header = DROPFILES()
    header.pFiles = ctypes.sizeof(DROPFILES)
    header.fWide = True

    data = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GHND, header.pFiles + len(data))
    if not handle:
        raise ctypes.WinError()
    ptr = kernel32.GlobalLock(handle)

    ctypes.memmove(ptr, ctypes.byref(header), ctypes.sizeof(header))
    ctypes.memmove(ptr + header.pFiles, data, len(data))
    kernel32.GlobalUnlock(handle)

    return handle


# DRAG-OUT: drag_files() / IDropSource.

DRAGDROP_S_DROP = 0x00040100
DRAGDROP_S_CANCEL = 0x00040101
DRAGDROP_S_USEDEFAULTCURSORS = 0x00040102

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002

DATADIR_GET = 1

IID_IDropSource = _guid("{00000121-0000-0000-C000-000000000046}")
IID_IDataObject = _guid("{0000010E-0000-0000-C000-000000000046}")
IID_IEnumFORMATETC = _guid("{00000103-0000-0000-C000-000000000046}")


class IDropSourceVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", QueryInterfaceFn),
        ("AddRef", AddRefFn),
        ("Release", ReleaseFn),
        ("QueryContinueDrag", QueryContinueDragFn),
        ("GiveFeedback", GiveFeedbackFn),
    ]


class IDataObjectVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", QueryInterfaceFn),
        ("AddRef", AddRefFn),
        ("Release", ReleaseFn),
        ("GetData", GetDataFn),
        ("GetDataHere", GetDataHereFn),
        ("QueryGetData", QueryGetDataFn),
        ("GetCanonicalFormatEtc", GetCanonicalFormatEtcFn),
        ("SetData", SetDataFn),
        ("EnumFormatEtc", EnumFormatEtcFn),
        ("DAdvise", DAdviseFn),
        ("DUnadvise", DUnadviseFn),
        ("EnumDAdvise", EnumDAdviseFn),
    ]


class IEnumFORMATETCVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", QueryInterfaceFn),
        ("AddRef", AddRefFn),
        ("Release", ReleaseFn),
        ("Next", NextFn),
        ("Skip", SkipFn),
        ("Reset", ResetFn),
        ("Clone", CloneFn),
    ]


def _is_hdrop(formatetc_ptr):
    fmt = formatetc_ptr[0]
    return fmt.cfFormat == CF_HDROP and (fmt.tymed & TYMED_HGLOBAL)


class _DragSession:
    """Per-drag COM objects for one DoDragDrop() call."""

    def __init__(self, paths):
        self.paths = list(paths)
        self._callbacks = []
        self._enum_index = 0

        self.drop_source_vtbl = IDropSourceVtbl(
            self._wrap(QueryInterfaceFn, self._query_interface),
            self._wrap(AddRefFn, self._add_ref),
            self._wrap(ReleaseFn, self._release),
            self._wrap(QueryContinueDragFn, self._query_continue_drag),
            self._wrap(GiveFeedbackFn, self._give_feedback),
        )
        self.drop_source = _ComObject(ctypes.cast(ctypes.byref(self.drop_source_vtbl), ctypes.c_void_p))

        self.data_object_vtbl = IDataObjectVtbl(
            self._wrap(QueryInterfaceFn, self._query_interface),
            self._wrap(AddRefFn, self._add_ref),
            self._wrap(ReleaseFn, self._release),
            self._wrap(GetDataFn, self._get_data),
            self._wrap(GetDataHereFn, self._not_impl),
            self._wrap(QueryGetDataFn, self._query_get_data),
            self._wrap(GetCanonicalFormatEtcFn, self._not_impl),
            self._wrap(SetDataFn, self._not_impl),
            self._wrap(EnumFormatEtcFn, self._enum_format_etc),
            self._wrap(DAdviseFn, self._not_impl),
            self._wrap(DUnadviseFn, self._not_impl),
            self._wrap(EnumDAdviseFn, self._not_impl),
        )
        self.data_object = _ComObject(ctypes.cast(ctypes.byref(self.data_object_vtbl), ctypes.c_void_p))

        self.enum_vtbl = IEnumFORMATETCVtbl(
            self._wrap(QueryInterfaceFn, self._query_interface),
            self._wrap(AddRefFn, self._add_ref),
            self._wrap(ReleaseFn, self._release),
            self._wrap(NextFn, self._enum_next),
            self._wrap(SkipFn, self._enum_skip),
            self._wrap(ResetFn, self._enum_reset),
            self._wrap(CloneFn, self._not_impl),
        )
        self.enum_object = _ComObject(ctypes.cast(ctypes.byref(self.enum_vtbl), ctypes.c_void_p))

        # Map COM object address -> interfaces accepted by QueryInterface.
        self._supported_iids = {
            ctypes.addressof(self.drop_source): (IID_IUnknown, IID_IDropSource),
            ctypes.addressof(self.data_object): (IID_IUnknown, IID_IDataObject),
            ctypes.addressof(self.enum_object): (IID_IUnknown, IID_IEnumFORMATETC),
        }

    def _wrap(self, functype, method):
        callback = functype(method)
        self._callbacks.append(callback)  # keep callback references alive
        return callback

    # IUnknown: no refcounting; object lifetime is scoped to drag_files().

    def _query_interface(self, this, riid, ppv):

        supported = self._supported_iids.get(this, ())
        wanted = _guid_bytes(riid[0])

        if any(wanted == _guid_bytes(iid) for iid in supported):
            ppv[0] = this
            return S_OK

        ppv[0] = None
        return E_NOINTERFACE

    def _add_ref(self, this):
        return 1

    def _release(self, this):
        return 1

    # IDropSource.

    def _query_continue_drag(self, this, escape_pressed, key_state):
        if escape_pressed:
            return DRAGDROP_S_CANCEL
        if not (key_state & (MK_LBUTTON | MK_RBUTTON)):
            return DRAGDROP_S_DROP
        return S_OK

    def _give_feedback(self, this, effect):
        return DRAGDROP_S_USEDEFAULTCURSORS

    # IDataObject: offer CF_HDROP only.

    def _query_get_data(self, this, formatetc):
        return S_OK if _is_hdrop(formatetc) else DV_E_FORMATETC

    def _get_data(self, this, formatetc, medium):
        if not _is_hdrop(formatetc):
            return DV_E_FORMATETC

        medium[0].tymed = TYMED_HGLOBAL
        medium[0].hGlobal = _build_hdrop_handle(self.paths)
        medium[0].pUnkForRelease = None
        _log(f"delivered {len(self.paths)} file(s) via CF_HDROP")
        return S_OK

    def _enum_format_etc(self, this, direction, ppenum):

        if direction != DATADIR_GET:
            return E_NOTIMPL

        self._enum_index = 0
        ppenum[0] = ctypes.addressof(self.enum_object)
        return S_OK

    def _enum_next(self, this, celt, rgelt, pcelt_fetched):

        fetched = 0

        while fetched < celt and self._enum_index < 1:
            rgelt[fetched] = FORMATETC(CF_HDROP, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
            self._enum_index += 1
            fetched += 1

        if pcelt_fetched:
            pcelt_fetched[0] = fetched

        return S_OK if fetched == celt else S_FALSE

    def _enum_skip(self, this, celt):
        self._enum_index += celt
        return S_OK if self._enum_index <= 1 else S_FALSE

    def _enum_reset(self, this):
        self._enum_index = 0
        return S_OK

    def _not_impl(self, this, *_args):
        return E_NOTIMPL


ole32.OleInitialize.argtypes = [ctypes.c_void_p]
ole32.DoDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

# COM apartment initialization is per-thread.
_ole_state = threading.local()


def _ensure_ole_ready():
    if not getattr(_ole_state, "ready", False):
        ole32.OleInitialize(None)
        _ole_state.ready = True


def drag_files(paths):
    """Block until a native drag-and-drop of the given file paths finishes.

    Returns the resulting DROPEFFECT (0 if the drag was cancelled)."""

    _ensure_ole_ready()

    session = _DragSession(paths)
    effect = wintypes.DWORD(DROPEFFECT_NONE)

    _log(f"drag started for {len(paths)} file(s)")

    ole32.DoDragDrop(
        ctypes.byref(session.data_object),
        ctypes.byref(session.drop_source),
        DROPEFFECT_COPY | DROPEFFECT_MOVE,
        ctypes.byref(effect),
    )

    effect_name = {DROPEFFECT_NONE: "none/cancelled", DROPEFFECT_COPY: "copy", DROPEFFECT_MOVE: "move"}
    _log(f"drag ended, effect={effect_name.get(effect.value, effect.value)}")

    return effect.value


# DRAG-IN: register_drop_target() / IDropTarget.

IID_IDropTarget = _guid("{00000122-0000-0000-C000-000000000046}")


class POINTL(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


DragEnterFn = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, POINTL, ctypes.POINTER(wintypes.DWORD)
)
DragOverFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD, POINTL, ctypes.POINTER(wintypes.DWORD))
DragLeaveFn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p)
DropFn = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, POINTL, ctypes.POINTER(wintypes.DWORD)
)


class IDropTargetVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", QueryInterfaceFn),
        ("AddRef", AddRefFn),
        ("Release", ReleaseFn),
        ("DragEnter", DragEnterFn),
        ("DragOver", DragOverFn),
        ("DragLeave", DragLeaveFn),
        ("Drop", DropFn),
    ]


ole32.RegisterDragDrop.argtypes = [wintypes.HWND, ctypes.c_void_p]
ole32.RevokeDragDrop.argtypes = [wintypes.HWND]
ole32.ReleaseStgMedium.argtypes = [ctypes.POINTER(STGMEDIUM)]
ole32.ReleaseStgMedium.restype = None  # actual signature is void


def _com_call(iface_ptr, index, functype, *args):
    """Call a COM vtable method by slot index."""

    vtbl = ctypes.cast(iface_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
    method = ctypes.cast(vtbl + index * ctypes.sizeof(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p))[0]
    return functype(method)(iface_ptr, *args)


def _offers_hdrop(data_obj):
    fmt = FORMATETC(CF_HDROP, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
    return _com_call(data_obj, 5, QueryGetDataFn, ctypes.byref(fmt)) == S_OK


def _extract_hdrop(data_obj):

    fmt = FORMATETC(CF_HDROP, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
    medium = STGMEDIUM()

    if _com_call(data_obj, 3, GetDataFn, ctypes.byref(fmt), ctypes.byref(medium)) != S_OK:
        return []

    try:
        if not medium.hGlobal:
            return []

        count = shell32.DragQueryFileW(medium.hGlobal, 0xFFFFFFFF, None, 0)
        files = []

        for index in range(count):
            length = shell32.DragQueryFileW(medium.hGlobal, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(medium.hGlobal, index, buffer, length + 1)
            files.append(buffer.value)

        return files
    finally:
        ole32.ReleaseStgMedium(ctypes.byref(medium))


class DropTarget:
    """OLE drop target for file drops onto one hwnd."""

    def __init__(self, hwnd, on_drop, effect=DROPEFFECT_COPY):
        _ensure_ole_ready()

        self.hwnd = hwnd
        self.on_drop = on_drop
        self.effect = effect
        self._accepts = False
        self._callbacks = []

        self.vtbl = IDropTargetVtbl(
            self._wrap(QueryInterfaceFn, self._query_interface),
            self._wrap(AddRefFn, self._add_ref),
            self._wrap(ReleaseFn, self._release),
            self._wrap(DragEnterFn, self._drag_enter),
            self._wrap(DragOverFn, self._drag_over),
            self._wrap(DragLeaveFn, self._drag_leave),
            self._wrap(DropFn, self._drop),
        )
        self.com_obj = _ComObject(ctypes.cast(ctypes.byref(self.vtbl), ctypes.c_void_p))

        ole32.RegisterDragDrop(hwnd, ctypes.byref(self.com_obj))

    def _wrap(self, functype, method):
        callback = functype(method)
        self._callbacks.append(callback)
        return callback

    def _query_interface(self, this, riid, ppv):
        wanted = _guid_bytes(riid[0])
        if wanted in (_guid_bytes(IID_IUnknown), _guid_bytes(IID_IDropTarget)):
            ppv[0] = this
            return S_OK
        ppv[0] = None
        return E_NOINTERFACE

    def _add_ref(self, this):
        return 1

    def _release(self, this):
        return 1

    def _drag_enter(self, this, data_obj, key_state, pt, pdw_effect):
        self._accepts = _offers_hdrop(data_obj)
        pdw_effect[0] = self.effect if self._accepts else DROPEFFECT_NONE
        return S_OK

    def _drag_over(self, this, key_state, pt, pdw_effect):
        pdw_effect[0] = self.effect if self._accepts else DROPEFFECT_NONE
        return S_OK

    def _drag_leave(self, this):
        self._accepts = False
        return S_OK

    def _drop(self, this, data_obj, key_state, pt, pdw_effect):

        paths = _extract_hdrop(data_obj) if self._accepts else []
        self._accepts = False
        pdw_effect[0] = self.effect if paths else DROPEFFECT_NONE

        if paths:
            _log(f"dropped {len(paths)} file(s) at ({pt.x}, {pt.y})")
            try:
                self.on_drop(paths, pt.x, pt.y)
            except Exception as e:
                _log(f"on_drop callback failed: {e!r}")

        return S_OK

    def close(self):
        ole32.RevokeDragDrop(self.hwnd)


def register_drop_target(hwnd, on_drop):
    """Register hwnd as a file drop target; keep returned object alive."""

    return DropTarget(hwnd, on_drop)


# File/terminal/Explorer/clipboard helpers.

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]
shell32.DragQueryFileW.restype = ctypes.c_uint
shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]


def open_file(path):
    os.startfile(path)


def open_terminal(path):
    try:
        subprocess.Popen(["wt", "-d", path])
    except OSError:
        subprocess.Popen(["cmd"], cwd=path)


def reveal_in_explorer(path):
    subprocess.Popen(["explorer", f"/select,{path}"])


FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
shell32.SHFileOperationW.restype = ctypes.c_int

# Selected SHFileOperation error codes (not standard Win32 error codes).
_SHFILEOP_ERRORS = {
    0x75: "DE_OPCANCELLED: operation cancelled by user",
    0x78: "DE_ACCESSDENIEDSRC: access denied on source (file locked, read-only, or lacking permission)",
    0x7C: "DE_INVALIDFILES: invalid source or destination path",
    0x81: "DE_FILENAMETOOLONG: filename too long",
}


def recycle(paths):
    """Move paths to Recycle Bin (SHFileOperationW)."""

    _ensure_ole_ready()  # required on the calling thread

    buffer = ctypes.create_unicode_buffer("\0".join(paths) + "\0")

    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = ctypes.cast(buffer, ctypes.c_wchar_p)
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT

    result = shell32.SHFileOperationW(ctypes.byref(op))

    if result != 0:
        detail = _SHFILEOP_ERRORS.get(result, "unknown SHFileOperation error")
        raise OSError(f"SHFileOperationW failed with code {result} (0x{result:x}): {detail}")


def set_clipboard_files(paths):
    _log(f"set_clipboard_files count={len(paths)} paths={paths}")
    handle = _build_hdrop_handle(paths)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise ctypes.WinError()

    try:
        if not user32.EmptyClipboard():
            kernel32.GlobalFree(handle)
            raise ctypes.WinError()

        if not user32.SetClipboardData(CF_HDROP, handle):
            # Ownership remains with caller when SetClipboardData fails.
            kernel32.GlobalFree(handle)
            raise ctypes.WinError()

        _log("set_clipboard_files success")
    finally:
        user32.CloseClipboard()


def get_clipboard_files():
    if not user32.OpenClipboard(None):
        _log("get_clipboard_files: OpenClipboard failed")
        return []

    try:
        handle = user32.GetClipboardData(CF_HDROP)

        if not handle:
            return []

        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        files = []

        for index in range(count):
            length = shell32.DragQueryFileW(handle, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(handle, index, buffer, length + 1)
            files.append(buffer.value)

        _log(f"get_clipboard_files count={len(files)} paths={files}")
        return files
    finally:
        user32.CloseClipboard()


# MONITORING: DirectoryWatcher.

FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

FILE_NOTIFY_CHANGE = (
    0x00000001  # FILE_NAME
    | 0x00000002  # DIR_NAME
    | 0x00000008  # SIZE
    | 0x00000010  # LAST_WRITE
)

kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = [
    ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
    ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
]
kernel32.ReadDirectoryChangesW.restype = wintypes.BOOL
kernel32.ReadDirectoryChangesW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL,
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, ctypes.c_void_p,
]
kernel32.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


class DirectoryWatcher:
    """Non-recursive ReadDirectoryChangesW watcher on a background thread."""

    def __init__(self, path, on_change):
        self._on_change = on_change
        self._stop_event = threading.Event()
        self._handle = kernel32.CreateFileW(
            path, FILE_LIST_DIRECTORY,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None,
        )

        if self._handle in (None, 0, INVALID_HANDLE_VALUE):
            raise ctypes.WinError()

        self._buffer = ctypes.create_string_buffer(4096)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        bytes_returned = wintypes.DWORD(0)

        while not self._stop_event.is_set():
            ok = kernel32.ReadDirectoryChangesW(
                self._handle, self._buffer, len(self._buffer), False,
                FILE_NOTIFY_CHANGE, ctypes.byref(bytes_returned), None, None,
            )

            if not ok:
                return

            self._on_change()

    def stop(self):
        self._stop_event.set()
        kernel32.CancelIoEx(self._handle, None)
        self._thread.join()
        kernel32.CloseHandle(self._handle)
