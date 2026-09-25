"""OpenGL 3D viewport for a selected B2W policy and Isaac Sim terrain.

The simulator owns physics, ground contacts, policy inference, and gamepad input.
This process renders the robot's URDF visual meshes from streamed rigid-body poses.
"""

import argparse
from collections import deque
import ctypes
import json
import math
import os
import shutil
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pyglet
from pyglet.gl import *  # noqa: F403

ROOT = Path(__file__).resolve().parents[1]
MESH_DIR = ROOT / "vendor/robot_lab/source/robot_lab/data/Robots/unitree/b2w_description/meshes"
CACHE_DIR = ROOT / ".cache/b2w-opengl-meshes"
NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
PARTS = ["base_link"] + [f"{leg}_{part}" for leg in ("FL", "FR", "RL", "RR")
                         for part in ("hip", "thigh", "calf", "foot")]

parser = argparse.ArgumentParser(description=__doc__)
model = parser.add_mutually_exclusive_group(required=True)
model.add_argument("--policy", type=Path)
model.add_argument("--checkpoint", type=Path)
parser.add_argument("--terrain", choices=("flat", "rough", "stair", "map"), required=True)
parser.add_argument("--terrain-family", default="random_rough")
parser.add_argument("--terrain-level", type=int, default=9)
parser.add_argument("--seed", type=int, default=2002)
parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cpu")
parser.add_argument("--fps", type=int, default=144)
parser.add_argument("--payload-urdf", type=Path,
                    help="Optional payload-enabled B2W URDF used by the Isaac Sim child process")
parser.add_argument("--stair-direction", choices=("up", "down"), default="up")
parser.add_argument("--stair-rise", type=float, default=0.14)
parser.add_argument("--stair-run", type=float, default=0.32)
parser.add_argument("--stair-steps", type=int, default=6)
parser.add_argument("--telemetry-port", type=int, default=0, help="0 selects a free local UDP port")
args = parser.parse_args()
if not 30 <= args.fps <= 240:
    parser.error("--fps must be between 30 and 240")
model_path = args.policy or args.checkpoint
if not model_path.is_file():
    parser.error(f"Model not found: {model_path}")
if args.payload_urdf:
    if not args.payload_urdf.is_file():
        parser.error(f"Payload URDF not found: {args.payload_urdf}")
    os.environ["B2W_PAYLOAD_URDF"] = str(args.payload_urdf.resolve())
if args.terrain == "rough" and not 0 <= args.terrain_level <= 9:
    parser.error("--terrain-level must be from 0 to 9")


def collada_mesh(path):
    """Extract visible COLLADA triangles in link coordinates; cache decimated base mesh."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / (path.stem + "-v2.npz")
    if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
        with np.load(target) as data:
            return data["vertices"], data["normals"]

    doc = ET.parse(path).getroot()
    geom = doc.find(".//c:geometry/c:mesh", NS)
    sources = {}
    for source in geom.findall("c:source", NS):
        floats = source.find("c:float_array", NS)
        if floats is not None:
            stride_node = source.find("c:technique_common/c:accessor", NS)
            stride = int(stride_node.get("stride", "3")) if stride_node is not None else 3
            sources[source.get("id")] = np.fromstring(floats.text, sep=" ", dtype=np.float32).reshape(-1, stride)
    vertices_source = {}
    for vertex in geom.findall("c:vertices", NS):
        entry = vertex.find("c:input[@semantic='POSITION']", NS)
        if entry is not None:
            vertices_source[vertex.get("id")] = entry.get("source").lstrip("#")
    node = doc.find(".//c:visual_scene/c:node/c:matrix", NS)
    transform = np.fromstring(node.text, sep=" ", dtype=np.float32).reshape(4, 4) if node is not None else np.eye(4)
    pieces = []
    for prim in list(geom):
        kind = prim.tag.rsplit("}", 1)[-1]
        if kind not in ("triangles", "polylist"):
            continue
        inputs = prim.findall("c:input", NS)
        stride = max(int(x.get("offset", "0")) for x in inputs) + 1
        vertex_input = next(x for x in inputs if x.get("semantic") == "VERTEX")
        source_id = vertices_source[vertex_input.get("source").lstrip("#")]
        index = np.fromstring(prim.find("c:p", NS).text, sep=" ", dtype=np.int32).reshape(-1, stride)
        positions = sources[source_id][index[:, int(vertex_input.get("offset", "0"))], :3]
        if kind == "triangles":
            triangles = positions.reshape(-1, 3, 3)
        else:
            counts = np.fromstring(prim.find("c:vcount", NS).text, sep=" ", dtype=np.int32)
            faces = []
            start = 0
            for count in counts:
                polygon = positions[start:start + count]
                if count >= 3:
                    faces.extend((polygon[0], polygon[j], polygon[j + 1]) for j in range(1, count - 1))
                start += count
            triangles = np.asarray(faces, dtype=np.float32)
        if len(triangles):
            pieces.append(triangles)
    triangles = np.concatenate(pieces)
    triangles = triangles @ transform[:3, :3].T + transform[:3, 3]
    edges1, edges2 = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    normals = np.cross(edges1, edges2)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    normals = np.repeat(normals[:, None, :], 3, axis=1).astype(np.float32).reshape(-1, 3)
    vertices = triangles.astype(np.float32).reshape(-1, 3)
    np.savez_compressed(target, vertices=vertices, normals=normals)
    return vertices, normals


def pose_matrix(position, quat):
    w, x, y, z = quat
    matrix = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), position[0]],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), position[1]],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), position[2]],
        [0, 0, 0, 1],
    ], dtype=np.float32)
    return (GLfloat * 16)(*matrix.T.ravel())


class Viewer(pyglet.window.Window):
    def __init__(self):
        super().__init__(1280, 800, caption=f"B2W {args.terrain} | Isaac Sim physics | OpenGL 3D", resizable=True,
                         vsync=False)
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", args.telemetry_port))
        self.telemetry_port = self.sock.getsockname()[1]
        self.sock.setblocking(False)
        self.snapshot = None
        self.pose_history = deque(maxlen=4)
        self.render_pose = None
        self.last_packet = 0.0
        self.started = time.monotonic()
        self.last_rate_time = self.started
        self.frame_count = 0
        self.packet_count = 0
        self.render_fps = 0.0
        self.physics_hz = 0.0
        self.yaw, self.pitch, self.distance = 45.0, 23.0, 3.5
        self.overview = False
        self.meshes = {}
        self.robot_lists = {}
        self.terrain_mesh = None
        self.terrain_lists = []
        self.last_status_update = 0.0
        self.status_label = pyglet.text.Label("Starting Isaac Sim...", x=18, font_size=13,
                                             color=(245, 248, 250, 255))
        self.map_label = pyglet.text.Label(
            f"Upstream map 80 x 160 m  |  {model_path.name}  |  M: map / follow",
            x=18, font_size=11, color=(190, 208, 220, 255))
        self.controls_label = pyglet.text.Label(
            "Gamepad: left stick move, right stick turn, A reset  |  Drag: orbit  |  Wheel: zoom",
            x=18, y=18, font_size=11, color=(190, 208, 220, 255))
        self.terrain_file = ROOT / ".cache" / f"b2w-opengl-terrain-{self.telemetry_port}.npz"
        if args.terrain != "flat":
            self.terrain_file.unlink(missing_ok=True)
        self.load_error = None
        self.log_path = ROOT / "logs/play_b2w_gamepad_opengl.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open("w", encoding="utf-8")
        shell = (shutil.which("pwsh") or shutil.which("powershell.exe") or
                 str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"))
        child_args = [shell, "-NoProfile", "-File", str(ROOT / "scripts/run_local.ps1"),
                      "scripts/play_b2w_gamepad.py", "--terrain", args.terrain,
                      "--device", args.device,
                      "--seed", str(args.seed), "--telemetry-port", str(self.telemetry_port),
                      "--checkpoint" if args.checkpoint else "--policy", str(model_path.resolve())]
        if args.terrain == "rough":
            child_args += ["--terrain-family", args.terrain_family, "--terrain-level", str(args.terrain_level),
                           "--terrain-mesh-file", str(self.terrain_file)]
        elif args.terrain == "stair":
            child_args += ["--stair-direction", args.stair_direction, "--stair-rise", str(args.stair_rise),
                           "--stair-run", str(args.stair_run), "--stair-steps", str(args.stair_steps),
                           "--terrain-mesh-file", str(self.terrain_file)]
        elif args.terrain == "map":
            child_args += ["--terrain-mesh-file", str(self.terrain_file)]
        self.sim = subprocess.Popen(
            child_args,
            cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            for part in PARTS:
                vertices, normals = collada_mesh(MESH_DIR / (part + ".dae"))
                self.meshes[part] = (vertices, normals)
                self.robot_lists[part] = self.compile_mesh(vertices, normals)
        except Exception as exc:
            self.load_error = str(exc)
            self.log.write("Mesh loading failed: " + repr(exc) + "\n")
            self.log.flush()
        self.viewer_log = (ROOT / "logs/b2w_viewer_performance.jsonl").open("w", encoding="utf-8")
        self.viewer_log.write(json.dumps({"renderer": pyglet.gl.gl_info.get_renderer(),
                                          "target_fps": args.fps, "device": args.device}) + "\n")
        self.viewer_log.flush()
        self.resources_closed = False
        pyglet.clock.schedule_interval(self.tick, 1 / args.fps)

    def compile_mesh(self, vertices, normals):
        """Store immutable geometry on the GPU, including robot links."""
        display_list = glGenLists(1)
        glNewList(display_list, GL_COMPILE)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, vertices.ctypes.data_as(ctypes.POINTER(GLfloat)))
        glNormalPointer(GL_FLOAT, 0, normals.ctypes.data_as(ctypes.POINTER(GLfloat)))
        glDrawArrays(GL_TRIANGLES, 0, len(vertices))
        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
        glEndList()
        return display_list

    def tick(self, _dt):
        if args.terrain != "flat" and self.terrain_mesh is None and self.terrain_file.is_file():
            try:
                with np.load(self.terrain_file) as data:
                    vertices = data["vertices"].astype(np.float32)
                    faces = data["faces"].astype(np.int32)
                triangles = vertices[faces]
                normals = np.cross(triangles[:, 1] - triangles[:, 0],
                                   triangles[:, 2] - triangles[:, 0])
                normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
                # Keep every triangle; cull distant 8 m chunks only in follow view.
                self.switch_to()
                centers = triangles.mean(axis=1)
                chunks = np.floor(centers[:, :2] / 8.0).astype(np.int32)
                _, groups = np.unique(chunks, axis=0, return_inverse=True)
                order = np.argsort(groups)
                for indices in np.split(order, np.flatnonzero(np.diff(groups[order])) + 1):
                    chunk = triangles[indices]
                    lo, hi = chunk.min(axis=(0, 1)), chunk.max(axis=(0, 1))
                    self.terrain_lists.append(((lo + hi) * .5, float(np.linalg.norm(hi - lo) * .5),
                        self.compile_mesh(chunk.reshape(-1, 3).copy(),
                            np.repeat(normals[indices, None, :], 3, axis=1).reshape(-1, 3).copy())))
                self.terrain_mesh = True
            except Exception as exc:
                self.load_error = f"Terrain mesh: {exc}"
        while True:
            try:
                packet, _ = self.sock.recvfrom(65535)
            except BlockingIOError:
                break
            self.snapshot = json.loads(packet)
            pose = np.asarray([self.snapshot["root_pos"] + self.snapshot["root_quat"]] + [
                self.snapshot["bodies"][part] + self.snapshot["body_quats"][part] for part in PARTS],
                dtype=np.float32)
            if self.pose_history and np.linalg.norm(pose[0, :3] - self.pose_history[-1][1][0, :3]) > 2:
                self.pose_history.clear()
            self.pose_history.append((self.snapshot.get("wall_time", time.perf_counter()), pose))
            self.last_packet = time.monotonic()
            self.packet_count += 1
        now = time.monotonic()
        if now - self.last_rate_time >= 1.0:
            elapsed = now - self.last_rate_time
            self.physics_hz = self.packet_count / elapsed
            self.render_fps = self.frame_count / elapsed
            self.packet_count = self.frame_count = 0
            self.last_rate_time = now
            self.viewer_log.write(json.dumps({"time": time.time(), "fps": self.render_fps,
                "policy_hz": self.physics_hz, "realtime": self.physics_hz * .02,
                "step": self.snapshot["step"] if self.snapshot else 0}) + "\n")
            self.viewer_log.flush()
        self.invalid = True

    def interpolated_pose(self):
        """Render one policy tick behind telemetry without changing simulation time."""
        if not self.pose_history:
            return None
        target = time.perf_counter() - self.snapshot.get("policy_dt", .02)
        while len(self.pose_history) > 2 and self.pose_history[1][0] <= target:
            self.pose_history.popleft()
        if len(self.pose_history) < 2:
            return self.pose_history[-1][1]
        t0, p0 = self.pose_history[0]
        t1, p1 = self.pose_history[1]
        alpha = np.clip((target - t0) / max(t1 - t0, 1e-6), 0.0, 1.0)
        result = p0 * (1.0 - alpha) + p1 * alpha
        # Normalized shortest-path quaternion interpolation.
        sign = np.where(np.sum(p0[:, 3:] * p1[:, 3:], axis=1, keepdims=True) < 0, -1, 1)
        quat = p0[:, 3:] * (1.0 - alpha) + p1[:, 3:] * sign * alpha
        result[:, 3:] = quat / np.maximum(np.linalg.norm(quat, axis=1, keepdims=True), 1e-8)
        return result

    def on_draw(self):
        self.frame_count += 1
        self.render_pose = self.interpolated_pose()
        glClearColor(.095, .13, .17, 1)
        self.clear()
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_NORMALIZE)
        light = (GLfloat * 4)(-2, 3, 5, 0)
        glLightfv(GL_LIGHT0, GL_POSITION, light)
        ambient = (GLfloat * 4)(.45, .45, .48, 1)
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, ambient)
        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(50.0, self.width / max(self.height, 1), .05, 600.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        target = self.render_pose[0, :3] if self.render_pose is not None else (0.0, 0.0, .5)
        if self.overview:
            target = (0.0, 0.0, 0.0)
        distance = 220.0 if self.overview else self.distance
        yaw, pitch = math.radians(self.yaw), math.radians(75.0 if self.overview else self.pitch)
        radius = distance * math.cos(pitch)
        eye = (target[0] - radius * math.cos(yaw),
               target[1] - radius * math.sin(yaw),
               target[2] + distance * math.sin(pitch))
        gluLookAt(*eye, target[0], target[1], target[2], 0, 0, 1)
        if args.terrain == "flat":
            self.draw_ground(target)
        elif self.terrain_mesh:
            glColor3f(.36, .43, .36)
            for center, radius, display_list in self.terrain_lists:
                if self.overview or np.linalg.norm(center[:2] - target[:2]) < max(32.0, self.distance * 2) + radius:
                    glCallList(display_list)
        if self.snapshot and self.meshes:
            self.draw_robot()
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluOrtho2D(0, self.width, 0, self.height)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        if self.load_error:
            status = "3D mesh error: " + self.load_error[:100]
        elif self.sim.poll() is not None:
            status = "Isaac Sim stopped; see logs/play_b2w_gamepad_opengl.log"
        elif args.terrain != "flat" and self.terrain_mesh is None:
            status = "Generating terrain in Isaac Sim..."
        elif self.snapshot:
            c = self.snapshot["command"]
            status = (f"Isaac Sim  |  {self.render_fps:.0f} FPS  |  realtime {self.physics_hz * .02:.2f}x  |  "
                      f"policy {self.physics_hz:.0f} Hz  |  "
                      f"step {self.snapshot['step']}  |  gamepad "
                      f"forward {c[0]:+.2f}  lateral {c[1]:+.2f}  turn {c[2]:+.2f}")
        else:
            status = "Starting Isaac Sim and loading B2W 3D meshes..."
        if time.monotonic() - self.last_status_update > .1:
            self.status_label.text = status
            self.last_status_update = time.monotonic()
        self.status_label.y = self.height - 28
        self.status_label.draw()
        if args.terrain == "map":
            self.map_label.y = self.height - 52
            self.map_label.draw()
        self.controls_label.draw()

    def draw_ground(self, target):
        ix, iy = math.floor(target[0]), math.floor(target[1])
        glDisable(GL_CULL_FACE)
        glBegin(GL_QUADS)
        glNormal3f(0, 0, 1)
        for x in range(ix - 12, ix + 12):
            for y in range(iy - 12, iy + 12):
                if (x + y) % 2:
                    glColor3f(.23, .30, .35)
                else:
                    glColor3f(.27, .35, .40)
                glVertex3f(x, y, -.015)
                glVertex3f(x + 1, y, -.015)
                glVertex3f(x + 1, y + 1, -.015)
                glVertex3f(x, y + 1, -.015)
        glEnd()

    def draw_robot(self):
        for index, part in enumerate(PARTS, 1):
            glPushMatrix()
            pose = self.render_pose[index]
            glMultMatrixf(pose_matrix(pose[:3], pose[3:]))
            if part == "base_link":
                glColor3f(.75, .80, .82)
            elif part.endswith("foot"):
                glColor3f(.16, .18, .20)
            else:
                glColor3f(.66, .70, .73)
            glCallList(self.robot_lists[part])
            glPopMatrix()

    def on_mouse_drag(self, _x, _y, dx, dy, _buttons, _modifiers):
        self.yaw += dx * .35
        self.pitch = max(-5, min(80, self.pitch + dy * .35))

    def on_mouse_scroll(self, _x, _y, _scroll_x, scroll_y):
        self.distance = max(1.1, min(220, self.distance * (0.88 ** scroll_y)))

    def on_key_press(self, symbol, _modifiers):
        if symbol == pyglet.window.key.ESCAPE:
            self.dispatch_event("on_close")
        elif symbol == pyglet.window.key.M and args.terrain == "map":
            self.overview = not self.overview

    def close(self):
        # Window.close() can be called directly (Escape), bypassing on_close.
        if getattr(self, "resources_closed", False):
            return
        self.resources_closed = True
        if self.sim.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.sim.pid), "/T", "/F"],
                           creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        self.sock.close()
        self.log.close()
        self.viewer_log.close()
        ctypes.WinDLL("winmm").timeEndPeriod(1)
        super().close()


if __name__ == "__main__":
    viewer = Viewer()
    pyglet.app.run()
