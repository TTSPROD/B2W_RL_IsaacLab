"""Local abstract Unix datagram client; native process owns DDS and deadlines."""
from __future__ import annotations
import json
import socket
import time
import uuid


class RejectedPolicyTick(RuntimeError):
    """Preserve the exact state/action/target that the native guard rejected."""
    def __init__(self, detail):
        reply=detail["accepted"]
        super().__init__(f"TARGET: {reply.get('error')}, {reply.get('fault')}")
        self.detail=detail


class WatchdogClient:
    def __init__(self, name):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.bind("\0b2w-client-" + uuid.uuid4().hex)
        self.socket.settimeout(.5)
        self.address = "\0" + name
        self.request_id = 0
        self.epoch = 0
        self.command_seq = 0
        self.inference_seq = 0

    def close(self):
        self.socket.close()

    def call(self, operation, *arguments, require_ok=True):
        self.request_id += 1
        packet = " ".join(map(str, (operation, self.request_id, *arguments))).encode("ascii")
        self.socket.sendto(packet, self.address)
        deadline = time.monotonic() + .5
        while True:
            self.socket.settimeout(max(.001, deadline-time.monotonic()))
            reply = json.loads(self.socket.recv(16384))
            if reply["id"] != self.request_id:
                if time.monotonic() >= deadline:
                    raise TimeoutError("IPC response id mismatch")
                continue
            if require_ok and not reply["ok"]:
                raise RuntimeError(f"{operation}: {reply.get('error')}, {reply.get('fault')}")
            return reply

    def state(self):
        return self.call("STATE")

    def recover(self):
        reply = self.call("RECOVER", self.epoch)
        self.epoch = reply["epoch"]
        self.command_seq = self.inference_seq = 0
        return reply

    def command(self, command):
        self.command_seq += 1
        return self.call("COMMAND", self.epoch, self.command_seq, time.monotonic_ns(), *command)

    def begin(self, state):
        self.inference_seq += 1
        return self.call("BEGIN", self.epoch, self.inference_seq, state["count"], self.command_seq)

    def target(self, motors, require_ok=True):
        return self.call("TARGET", self.epoch, self.inference_seq,
                         *(value for motor in motors for value in motor), require_ok=require_ok)

    def arm(self):
        return self.call("ARM", self.epoch)

    def stop(self):
        return self.call("STOP", self.epoch)


def policy_tick(client, runtime, command, *, refresh_command=True):
    if refresh_command:
        client.command(command)
    state = client.state()
    if state["fault"]:
        raise RuntimeError("Native watchdog latched: " + state["fault"])
    begin = client.begin(state)
    start = time.monotonic_ns()
    cpu_start = time.thread_time_ns()
    try:
        result = runtime.step(state, command, (start-begin["command_ns"])/1e9)
    except (ValueError, RuntimeError):
        client.call("FAIL", client.epoch, require_ok=False)
        raise
    end = time.monotonic_ns()
    cpu_end = time.thread_time_ns()
    accepted = client.target(result["motors"],require_ok=False)
    detail={"state":state,"command":command,"begin":begin,"accepted":accepted,
            "inference_start_ns":start,"inference_end_ns":end,
            "inference_cpu_ns":cpu_end-cpu_start,**result}
    if not accepted["ok"]:
        raise RejectedPolicyTick(detail)
    return detail
