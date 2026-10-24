import binascii
import json
from pathlib import Path

import pytest
from arduino_hid_emulator.protocol import decode, encode, request, ProtocolError


def test_contract_vectors():
    data = json.loads((Path(__file__).parent/'fixtures/hid-v1-vectors.json').read_text())
    assert binascii.crc_hqx(b'123456789', 0xFFFF) == 0x29B1
    for vector in data['vectors']:
        assert encode(vector['body']) == vector['frame'].encode()
        frame = decode(vector['frame'].encode(), vector['body'][:2])
        assert frame.command_id > 0


@pytest.mark.parametrize('body', [
    'Q1 0123456789ABCDEF 1 0 HB\nkey_press a',
    'Q1 0123456789ABCDEF 1 0 HB\r', 'Q1 0123456789ABCDEF 1 0 ё',
    'Q1 0123456789ABCDEF 1 0  HB', 'Q1 0123456789ABCDEF 1 0 HB\x00',
])
def test_noncanonical_bodies(body):
    with pytest.raises(ProtocolError):
        encode(body)


@pytest.mark.parametrize('frame', [
    b'True\n', b'\xff\n', b'R2 0123456789ABCDEF 1 0 DONE OK *0000\n',
    b'X'*128+b'\n', b'R1 0123456789ABCDEF 1 0 DONE OK *0000\n',
    encode('R1 0123456789ABCDEF 01 0 DONE OK'),
    encode('R1 0123456789ABCDEF 4294967296 0 DONE OK'),
    encode('R1 0000000000000000 1 0 DONE OK'),
])
def test_malformed_frames(frame):
    with pytest.raises(ProtocolError):
        decode(frame, 'R1')


def test_request_checks_overflow_and_injection():
    for command_id in (-1, 0, True, 2**32):
        with pytest.raises(ProtocolError):
            request('0123456789ABCDEF', command_id, 0, 'HB')
