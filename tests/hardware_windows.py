"""Explicit opt-in Leonardo test. Own Tk window receives only fixed test input.

Run: python tests/hardware_windows.py --port COM3 --output build/hardware.json
Never reads other windows or files, never changes another application's focus.
Physical USB unplug/replug and host sleep are separate manual acceptance tests.
"""
import argparse
import ctypes
import json
import threading
import time
import tkinter as tk
from dataclasses import asdict
from pathlib import Path

from arduino_hid_emulator import HidDevice, Outcome
from arduino_hid_emulator.protocol import request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=ctypes.c_void_p
    user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    user32.GetAncestor.restype=ctypes.c_void_p
    user32.LoadKeyboardLayoutW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint]
    user32.LoadKeyboardLayoutW.restype=ctypes.c_void_p
    user32.ActivateKeyboardLayout.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    user32.ActivateKeyboardLayout.restype=ctypes.c_void_p
    user32.GetKeyState.argtypes=[ctypes.c_int]
    user32.GetAsyncKeyState.argtypes=[ctypes.c_int]
    user32.GetAsyncKeyState.restype=ctypes.c_short
    root=tk.Tk()
    root.title('Arduino HID v1 — isolated hardware acceptance')
    root.geometry('680x260+120+100')
    tk.Label(root,text='Fixed HID test input only. Keep this window active until it closes.').pack()
    editor=tk.Text(root,width=70,height=8)
    editor.pack()
    root.update()
    hwnd=user32.GetAncestor(root.winfo_id(),2)
    layout=user32.LoadKeyboardLayoutW('00000409',0)
    if not layout:
        raise RuntimeError('US keyboard layout unavailable')
    user32.ActivateKeyboardLayout(layout,0) # own GUI thread only
    events=[]
    pressed=threading.Event()
    released=threading.Event()
    capture={'enabled':False}
    def event(kind,e):
        if capture['enabled']:
            events.append((kind,e.keysym,time.perf_counter()))
            if e.keysym.lower()=='c':
                (pressed if kind=='down' else released).set()
    editor.bind('<KeyPress>',lambda e:event('down',e),add=True)
    editor.bind('<KeyRelease>',lambda e:event('up',e),add=True)
    root.after(200,editor.focus_force)
    result={'port':args.port,'checks':{},'measurements':{}}
    finished=threading.Event()
    errors=[]

    def guard():
        if user32.GetForegroundWindow()!=hwnd:
            raise RuntimeError('Test window lost focus; no further HID input')
        if any(user32.GetAsyncKeyState(v)&0x8000 for v in (16,17,18,91,92)):
            raise RuntimeError('External modifier is held')

    def require(value):
        if not value.completed:
            raise RuntimeError('Unexpected operation outcome: '+value.code)

    def worker():
        client=None
        try:
            client=HidDevice(args.port)
            result['capabilities']=asdict(client.capabilities)
            guard()
            require(client.begin(1))
            # Expected final text: A + space + newline + b. Includes erased a.
            for usage,mask in [(4,2),(44,0),(40,0),(4,0),(42,0),(5,0)]:
                guard(); last=client.tap(1,usage,mask); require(last); time.sleep(0.02)
            result['checks']['basic_operations_completed']=True
            # Replayed terminal action must ACK without inserting a second b.
            with client._writer:
                client._serial.write(request(client.session,last.command_id,1,'TAP',5,0,10))
                corrupt=bytearray(request(client.session,4294967295,1,'TAP',4,0,10))
                corrupt[-2]=ord('0') if corrupt[-2]!=ord('0') else ord('1')
                client._serial.write(corrupt)
                client._serial.write(b'X'*200+b'\nkey_press a\n')
            time.sleep(.1)
            result['checks']['duplicate_and_invalid_frames_preserve_session']=client.healthy
            require(client.cancel(1))
            require(client.begin(2))
            capture['enabled']=True
            guard()
            require(client.down(2,6)) # c, bounded to 100ms even without UP
            assert pressed.wait(0.5) and released.wait(0.5)
            press=next(t for k,key,t in events if k=='down' and key.lower()=='c')
            release=next(t for k,key,t in events if k=='up' and key.lower()=='c')
            result['measurements']['down_auto_release_event_ms']=round((release-press)*1000,3)
            result['checks']['down_auto_release_observed']=True
            require(client.up(2))
            require(client.cancel(2))
            require(client.begin(3))
            events.clear(); pressed.clear(); released.clear()
            tap_result=[]
            guard()
            operation=threading.Thread(target=lambda:tap_result.append(client.tap(3,6,0,100)))
            operation.start()
            assert pressed.wait(0.5)
            start=time.perf_counter()
            require(client.cancel(3))
            cancel_ms=(time.perf_counter()-start)*1000
            assert released.wait(0.5)
            operation.join(0.5)
            assert tap_result and tap_result[0].completed
            result['measurements']['cancel_ack_ms']=round(cancel_ms,3)
            result['checks']['cancel_under_100ms']=cancel_ms<100
            result['checks']['cancelled_generation_rejected']=client.tap(3,4).outcome is Outcome.NOT_EXECUTED
            capture['enabled']=False
            time.sleep(0.15)
            result['checks']['no_owned_modifiers_held']=not any(user32.GetAsyncKeyState(v)&0x8000 for v in (16,17,18,91,92))
            require(client.begin(4))
            time.sleep(1.3) # automatic heartbeat must outlive firmware lease
            require(client.cancel(4))
            result['checks']['heartbeat_during_idle']=True
            client.close(); client=None
            # Actual serial control-line loss while a modifier is held; USB
            # remains attached, allowing a real zero report to reach Windows.
            client=HidDevice(args.port)
            require(client.begin(1)); guard()
            require(client.down(1,104,2)) # Shift+F13: no text or application hotkey
            time.sleep(.01)
            start=time.perf_counter()
            client._serial.dtr=False
            deadline=time.monotonic()+.5
            while user32.GetAsyncKeyState(16)&0x8000 and time.monotonic()<deadline:
                time.sleep(.001)
            elapsed=(time.perf_counter()-start)*1000
            result['measurements']['dtr_loss_release_observed_ms']=round(elapsed,3)
            result['checks']['dtr_loss_releases_shift']=not(user32.GetAsyncKeyState(16)&0x8000)
            client.close(); client=None
            # New instance/session; old generation never resumes automatically.
            client=HidDevice(args.port,heartbeat=False)
            require(client.begin(1))
            time.sleep(1.15)
            value=client.tap(1,4)
            result['checks']['expired_lease_rejected_without_hid']=value.outcome is Outcome.NOT_EXECUTED and value.code=='BAD_SESSION'
            client.close(); client=None
        except BaseException as exc:
            errors.append(type(exc).__name__+': '+str(exc))
        finally:
            if client is not None:
                client.close()
            finished.set()

    def poll():
        if finished.is_set():
            text=editor.get('1.0','end-1c')
            result['checks']['exact_basic_text_and_two_probe_characters']=text=='A \nbcc'
            result['errors']=errors
            result['passed']=not errors and all(result['checks'].values())
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result,indent=2))
            root.destroy()
        else:
            root.after(20,poll)
    root.after(500,lambda:threading.Thread(target=worker,daemon=True).start())
    root.after(550,poll)
    root.mainloop()
    raise SystemExit(0 if result.get('passed') else 1)


if __name__=='__main__':
    main()
