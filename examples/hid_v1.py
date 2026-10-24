"""Opt-in raw keyboard example; reads no text files. Select a prepared target."""
import argparse
from arduino_hid_emulator import HidDevice


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--tap-a',action='store_true',help='Actually press raw US A key once')
    args=parser.parse_args()
    with HidDevice(args.port) as device:
        print(device.capabilities)
        if args.tap_a:
            if not device.begin(1).completed:
                raise RuntimeError('BEGIN failed')
            result=device.tap(1,4)
            print(result.outcome.value,result.code)
            device.cancel(1)


if __name__=='__main__':
    main()
