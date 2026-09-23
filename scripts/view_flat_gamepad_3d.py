"""OpenGL 3D viewport for the project's headless Isaac Sim B2W run.

The simulator owns physics, ground contacts, policy inference, and gamepad input.
This process renders the robot's URDF visual meshes from streamed rigid-body poses.
"""

import ctypes
import json
import math
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
PORT = 29781
NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
PARTS = ["base_link"] + [f"{leg}_{part}" for leg in ("FL", "FR", "RL", "RR")
                         for part in ("hip", "thigh", "calf", "foot")]


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
        super().__init__(1280, 800, caption="B2W | Isaac Sim physics | OpenGL 3D", resizable=True,
                         vsync=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", PORT))
        self.sock.setblocking(False)
        self.snapshot = None
        self.last_packet = 0.0
        self.started = time.monotonic()
        self.yaw, self.pitch, self.distance = 45.0, 23.0, 3.5
        self.meshes = {}
        self.load_error = None
        self.log_path = ROOT / "logs/play_flat_gamepad_opengl.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open("w", encoding="utf-8")
        self.sim = subprocess.Popen(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/run_local.ps1"),
             "scripts/play_flat_gamepad.py", "--telemetry-port", str(PORT)],
            cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            for part in PARTS:
                vertices, normals = collada_mesh(MESH_DIR / (part + ".dae"))
                self.meshes[part] = (vertices, normals)
        except Exception as exc:
            self.load_error = str(exc)
            self.log.write("Mesh loading failed: " + repr(exc) + "\n")
            self.log.flush()
        pyglet.clock.schedule_interval(self.tick, 1 / 30)

    def tick(self, _dt):
        while True:
            try:
                packet, _ = self.sock.recvfrom(65535)
            except BlockingIOError:
                break
            self.snapshot = json.loads(packet)
            self.last_packet = time.monotonic()
        self.invalid = True

    def on_draw(self):
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
        gluPerspective(50.0, self.width / max(self.height, 1), .05, 200.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        target = self.snapshot["root_pos"] if self.snapshot else (0.0, 0.0, .5)
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        radius = self.distance * math.cos(pitch)
        eye = (target[0] - radius * math.cos(yaw),
               target[1] - radius * math.sin(yaw),
               target[2] + self.distance * math.sin(pitch))
        gluLookAt(*eye, target[0], target[1], target[2], 0, 0, 1)
        self.draw_ground(target)
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
        elif self.snapshot:
            c = self.snapshot["command"]
            status = (f"Isaac Sim  |  step {self.snapshot['step']}  |  gamepad "
                      f"forward {c[0]:+.2f}  lateral {c[1]:+.2f}  turn {c[2]:+.2f}")
        elif self.sim.poll() is not None:
            status = "Isaac Sim failed to start; see logs/play_flat_gamepad_opengl.log"
        else:
            status = "Starting Isaac Sim and loading B2W 3D meshes..."
        pyglet.text.Label(status, x=18, y=self.height - 28, font_size=13,
                          color=(245, 248, 250, 255)).draw()
        pyglet.text.Label("Gamepad: left stick move, right stick turn  |  Drag: orbit  |  Wheel: zoom",
                          x=18, y=18, font_size=11, color=(190, 208, 220, 255)).draw()

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
        bodies = self.snapshot["bodies"]
        quats = self.snapshot["body_quats"]
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        for part, (vertices, normals) in self.meshes.items():
            if part not in bodies or part not in quats:
                continue
            glPushMatrix()
            glMultMatrixf(pose_matrix(bodies[part], quats[part]))
            if part == "base_link":
                glColor3f(.75, .80, .82)
            elif part.endswith("foot"):
                glColor3f(.16, .18, .20)
            else:
                glColor3f(.66, .70, .73)
            glVertexPointer(3, GL_FLOAT, 0, vertices.ctypes.data_as(ctypes.POINTER(GLfloat)))
            glNormalPointer(GL_FLOAT, 0, normals.ctypes.data_as(ctypes.POINTER(GLfloat)))
            glDrawArrays(GL_TRIANGLES, 0, len(vertices))
            glPopMatrix()
        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

    def on_mouse_drag(self, _x, _y, dx, dy, _buttons, _modifiers):
        self.yaw += dx * .35
        self.pitch = max(-5, min(80, self.pitch + dy * .35))

    def on_mouse_scroll(self, _x, _y, _scroll_x, scroll_y):
        self.distance = max(1.1, min(18, self.distance * (0.88 ** scroll_y)))

    def on_key_press(self, symbol, _modifiers):
        if symbol == pyglet.window.key.ESCAPE:
            self.close()

    def on_close(self):
        if self.sim.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.sim.pid), "/T", "/F"],
                           creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        self.sock.close()
        self.log.close()
        super().on_close()


if __name__ == "__main__":
    viewer = Viewer()
    pyglet.app.run()
