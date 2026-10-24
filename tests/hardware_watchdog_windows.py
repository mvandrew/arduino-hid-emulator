"""Opt-in WDT test for HIDV1_FAULT_INJECTION image; restore production afterward.

Uses only Shift+F13 in its own Tk window, then freezes firmware via test-only !.
Records actual USB re-enumeration and release of the modifier on reset.
"""
import argparse
import ctypes
import json
import threading
import time
import tkinter as tk
from pathlib import Path

from arduino_hid_emulator import HidDevice, ConnectionError
from serial.tools.list_ports import comports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=tk.Tk(); root.title('HID v1 — watchdog reset test (Shift+F13 only)')
    tk.Label(root,text='Watchdog test: keep this isolated window active for several seconds.').pack(padx=30,pady=30)
    root.update()
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetForegroundWindow.restype=ctypes.c_void_p
    user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    user.GetAncestor.restype=ctypes.c_void_p
    user.GetAsyncKeyState.argtypes=[ctypes.c_int]
    user.GetAsyncKeyState.restype=ctypes.c_short
    hwnd=user.GetAncestor(root.winfo_id(),2)
    root.after(200,root.focus_force)
    result={'port':args.port,'checks':{},'measurements':{},'errors':[]}
    done=threading.Event()

    def run():
        client=None
        try:
            client=HidDevice(args.port)
            if user.GetForegroundWindow()!=hwnd:
                raise RuntimeError('Own test window not active')
            if any(user.GetAsyncKeyState(k)&0x8000 for k in (16,17,18,91,92)):
                raise RuntimeError('External modifiers held')
            assert client.begin(1).completed
            assert client.down(1,104,2).completed
            time.sleep(0.01)
            assert user.GetAsyncKeyState(16)&0x8000
            result['checks']['shift_down_observed']=True
            before=client.session
            start=time.perf_counter()
            with client._writer:
                client._serial.write(b'!')
            disappeared=False
            returned=False
            release_at=None
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                elapsed=time.perf_counter()-start
                if release_at is None and not (user.GetAsyncKeyState(16)&0x8000):
                    release_at=elapsed
                present=args.port in [p.device for p in comports()]
                if not present:
                    disappeared=True
                if disappeared and present:
                    returned=True
                    break
                time.sleep(0.02)
            result['checks']['usb_disappeared_on_wdt']=disappeared
            result['checks']['usb_reenumerated']=returned
            result['checks']['shift_released_on_reset']=release_at is not None
            result['measurements']['shift_release_seconds']=round(release_at,4) if release_at is not None else None
            result['measurements']['port_return_seconds']=round(time.perf_counter()-start,4)
            result['checks']['old_client_failed_closed']=not client.healthy
            client.close(); client=None
            if returned:
                # A port can be listed before Windows allows CreateFile again.
                deadline=time.monotonic()+5
                while True:
                    try:
                        client=HidDevice(args.port)
                        break
                    except ConnectionError:
                        if time.monotonic()>=deadline:
                            raise
                        time.sleep(.2)
                result['checks']['new_session_after_reset']=client.session!=before
                result['checks']['new_generation_requires_begin']=client.tap(1,4).code=='STALE_GENERATION'
                result['checks']['handshake_after_wdt']=client.capabilities.firmware=='1.1.0'
                result['checks']['no_modifier_held_after_reconnect']=not(user.GetAsyncKeyState(16)&0x8000)
        except BaseException as exc:
            result['errors'].append(type(exc).__name__+': '+str(exc))
        finally:
            if client:
                client.close()
            done.set()

    def poll():
        if done.is_set():
            result['passed']=not result['errors'] and bool(result['checks']) and all(result['checks'].values())
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result,indent=2))
            root.destroy()
        else:
            root.after(20,poll)
    root.after(500,lambda:threading.Thread(target=run,daemon=True).start())
    root.after(550,poll)
    root.mainloop()
    raise SystemExit(0 if result.get('passed') else 1)


if __name__=='__main__':
    main()
