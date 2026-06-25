"""Why is injected input not delivered? Identify the desktop/session state."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
wtsapi = ctypes.WinDLL("wtsapi32", use_last_error=True)

UOI_NAME = 2
DESKTOP_READOBJECTS = 0x0001

user32.GetThreadDesktop.restype = wintypes.HANDLE
user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                             ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]


def obj_name(h):
    if not h:
        return f"<null, err={ctypes.get_last_error()}>"
    buf = ctypes.create_unicode_buffer(256)
    need = wintypes.DWORD()
    user32.GetUserObjectInformationW(h, UOI_NAME, buf, ctypes.sizeof(buf), ctypes.byref(need))
    return buf.value


cur_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
input_desktop = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)

print("current thread desktop :", obj_name(cur_desktop))
print("active INPUT desktop   :", obj_name(input_desktop))

# session ids
pid = kernel32.GetCurrentProcessId()
sess = wintypes.DWORD()
kernel32.ProcessIdToSessionId(pid, ctypes.byref(sess))
console = wtsapi.WTSGetActiveConsoleSessionId()
print(f"process session id     : {sess.value}")
print(f"active console session : {console}")

# GetLastInputInfo: ms since last real user input (huge/odd in headless)
class LASTINPUT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

li = LASTINPUT(); li.cbSize = ctypes.sizeof(LASTINPUT)
user32.GetLastInputInfo(ctypes.byref(li))
tick = kernel32.GetTickCount()
print(f"idle since last input  : {(tick - li.dwTime)/1000.0:.1f} s")

locked = obj_name(input_desktop) not in ("Default",)
same = (obj_name(cur_desktop) == obj_name(input_desktop))
print()
print(f"my desktop == input desktop : {same}")
print(f"input desktop is a secure/locked desktop (not 'Default'): {locked}")
if not same:
    print("DIAGNOSIS: my process is NOT on the active input desktop -> "
          "injected input goes to a background desktop (locked or switched session).")
elif obj_name(input_desktop) == "Default":
    print("DIAGNOSIS: on Default input desktop but cursor/SetCursorPos dead -> "
          "headless/no physical console attached.")
