"""Select this worker's performance cores without changing system policy."""
import ctypes
import os
import struct


def select_performance_cores():
    import psutil
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    query = kernel.GetSystemCpuSetInformation
    query.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p, ctypes.c_uint32]
    query.restype = ctypes.c_int
    required = ctypes.c_uint32()
    query(None, 0, ctypes.byref(required), None, 0)
    buffer = ctypes.create_string_buffer(required.value)
    if not query(buffer, len(buffer), ctypes.byref(required), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    rows = []
    offset = 0
    while offset < required.value:
        size, kind = struct.unpack_from('<II', buffer.raw, offset)
        if size < 8:
            raise RuntimeError('Invalid CPU-set descriptor')
        if kind == 0:
            values = struct.unpack_from('<IHBBBBBBIQ', buffer.raw, offset + 8)
            rows.append(dict(zip(('id', 'group', 'logical', 'core', 'cache', 'numa', 'efficiency', 'flags', 'scheduling', 'tag'), values)))
        offset += size
    if not rows or {r['group'] for r in rows} != {0}:
        raise RuntimeError('Expected the qualified single processor group')
    fastest = max(r['efficiency'] for r in rows)
    chosen = [r['logical'] for r in rows if r['efficiency'] == fastest]
    if fastest == min(r['efficiency'] for r in rows) or chosen != list(range(16)):
        raise RuntimeError('CPU topology differs from the qualified i9-14900HX laptop')
    process = psutil.Process(os.getpid())
    original = process.cpu_affinity()
    process.cpu_affinity(chosen)
    return {'cpu_sets': rows, 'original_affinity': original, 'selected_affinity': process.cpu_affinity(),
            'scope': 'This process and its subsequently created children only; no power-plan or driver changes'}
