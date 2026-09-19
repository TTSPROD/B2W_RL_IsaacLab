"""Windows Xbox input for simulator-only B2W velocity commands (no robot transport)."""
from dataclasses import dataclass
import ctypes
import math
import os

LB, A, B, X = 0x0100, 0x1000, 0x2000, 0x4000

@dataclass(frozen=True)
class PadState:
    connected: bool = False
    packet: int = 0
    buttons: int = 0
    lx: int = 0
    ly: int = 0
    rx: int = 0
    ry: int = 0

class XInputController:
    def __init__(self, index=0):
        if os.name != 'nt' or index not in range(4):
            raise ValueError('Requires Windows and XInput index0..3')
        class Gamepad(ctypes.Structure):
            _fields_ = [('buttons', ctypes.c_uint16), ('lt', ctypes.c_uint8), ('rt', ctypes.c_uint8),
                        ('lx', ctypes.c_int16), ('ly', ctypes.c_int16), ('rx', ctypes.c_int16), ('ry', ctypes.c_int16)]
        class State(ctypes.Structure):
            _fields_ = [('packet', ctypes.c_uint32), ('pad', Gamepad)]
        self._state_type, self.index = State, index
        self._dll = ctypes.WinDLL('xinput1_4.dll')
        self._get = self._dll.XInputGetState
        self._get.argtypes = [ctypes.c_uint32, ctypes.POINTER(State)]
        self._get.restype = ctypes.c_uint32
        if ctypes.sizeof(State) != 16:
            raise RuntimeError('Unexpected XINPUT_STATE ABI')

    def read(self):
        state = self._state_type()
        result = self._get(self.index, ctypes.byref(state))
        if result == 1167:
            return PadState()
        if result != 0:
            raise OSError(result, 'XInputGetState failed')
        return PadState(True, state.packet, state.pad.buttons, state.pad.lx, state.pad.ly, state.pad.rx, state.pad.ry)


def axis(value, dead_zone=.15):
    if not 0 <= dead_zone < 1 or not math.isfinite(value):
        raise ValueError('Invalid stick/dead zone')
    normalized = max(-1., min(1., value / 32767.))
    return 0. if abs(normalized) <= dead_zone else math.copysign((abs(normalized) - dead_zone) / (1. - dead_zone), normalized)

class CommandMapper:
    """Hold LB to drive; release/disconnect/B immediately requests zero velocity."""
    def __init__(self):
        self.previous_buttons = 0
        self.command = (0., 0., 0.)
        self.blocked = False

    def advance(self, state, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('Invalid command timestep')
        rising = state.buttons & ~self.previous_buttons if state.connected else 0
        self.previous_buttons = state.buttons if state.connected else 0
        reset, camera = bool(rising & A), bool(rising & X)
        if not state.connected or state.buttons & B:
            self.blocked = True
        elif not state.buttons & LB:
            self.blocked = False
        if not state.connected or not state.buttons & LB or self.blocked or reset:
            self.command = (0., 0., 0.)
        else:
            # Robot axes: x forward, y left, positive yaw left.
            target = (.5 * axis(state.ly), -.3 * axis(state.lx), -.5 * axis(state.rx))
            self.command = tuple(old + max(-rate * dt, min(rate * dt, new - old))
                                 for old, new, rate in zip(self.command, target, (.8, .6, 1.2)))
        return self.command, reset, camera
