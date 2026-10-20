#!/usr/bin/env python3
"""Crayonbox: image/video MCP server (generate_image, generate_video, list_models).

Talks to any OpenAI-compatible provider. Configure once in ~/.config/crayonbox.json:
  {"base_url": "https://api.example.com/v1", "api_key": "sk-..."}
Optional keys: image_model, video_model, image_size (1K), video_size (720P), model_ttl (600).
Anything in the environment (CRAYONBOX_BASE_URL, CRAYONBOX_API_KEY, ...) wins over the file.
"""
import base64
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CONFIG_PATH = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                           "crayonbox.json")


def _load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


CFG = _load_config()


def opt(env_name, cfg_name, default=""):
    return os.environ.get(env_name) or CFG.get(cfg_name) or default


BASE = opt("CRAYONBOX_BASE_URL", "base_url").rstrip("/")
KEY = opt("CRAYONBOX_API_KEY", "api_key")
OUTPUT_DIR = os.path.expanduser(opt("CRAYONBOX_OUTPUT_DIR", "output_dir"))
ROOT = BASE[:-3] if BASE.endswith("/v1") else BASE
RATIOS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "2:3", "3:2"}
DONE = {"completed", "succeeded", "success"}
IMAGE_HINTS = ("image", "imagen", "dall-e", "dalle", "flux", "seedream", "diffusion",
               "banana", "kolors", "recraft", "hidream", "draw")
VIDEO_HINTS = ("video", "veo", "sora", "kling", "seedance", "wan", "hailuo", "runway",
               "pixverse", "imagine", "minimax")
SKIP_HINTS = ("embed", "rerank", "whisper", "tts", "audio", "moderation")

_cache = {"at": 0.0, "ids": []}


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def api(path, body=None, method=None, timeout=180):
    if not BASE:
        raise ApiError("no base URL: run `crayonbox setup` or set CRAYONBOX_BASE_URL")
    url = path if path.startswith("http") else BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:800]
        raise ApiError("HTTP %d from %s: %s" % (e.code, url, detail), status=e.code) from e
    except urllib.error.URLError as e:
        raise ApiError("cannot reach %s: %s" % (url, e.reason)) from e


def model_ids():
    ttl = int(opt("CRAYONBOX_MODEL_TTL", "model_ttl", "600"))
    if time.time() - _cache["at"] < ttl:
        return _cache["ids"]
    resp = api("/models")
    rows = resp.get("data") if isinstance(resp, dict) else resp
    ids = [m.get("id") for m in rows or [] if isinstance(m, dict) and m.get("id")]
    if not ids:
        raise ApiError("GET /models returned no model ids: " + json.dumps(resp, ensure_ascii=False)[:500])
    _cache.update(at=time.time(), ids=ids)
    return ids


def version_key(model_id):
    nums = re.findall(r"\d+(?:\.\d+)*", model_id)
    return tuple(int(n) if n.isdigit() else float(n) for part in nums for n in part.split("."))


def classify_model(model_id):
    low = model_id.lower()
    if any(s in low for s in SKIP_HINTS):
        return "other"
    if any(h in low for h in VIDEO_HINTS):
        return "video"
    if any(h in low for h in IMAGE_HINTS):
        return "image"
    return "chat"


def pick_model(kind, explicit=None):
    if explicit:
        return explicit
    override = opt("CRAYONBOX_IMAGE_MODEL" if kind == "image" else "CRAYONBOX_VIDEO_MODEL",
                   "image_model" if kind == "image" else "video_model")
    if override:
        return override
    candidates = [m for m in model_ids() if classify_model(m) == kind]
    if not candidates:
        raise ApiError("no %s model found; pass model explicitly or set %s"
                       % (kind, "CRAYONBOX_IMAGE_MODEL" if kind == "image" else "CRAYONBOX_VIDEO_MODEL"))
    return max(candidates, key=lambda m: (version_key(m), "flash" in m.lower(), len(m)))


def list_models():
    ids = model_ids()
    groups = {"image": [], "video": [], "chat": [], "other": []}
    for m in ids:
        groups[classify_model(m)].append(m)
    lines = []
    for kind in ("image", "video", "chat", "other"):
        names = groups[kind]
        if not names:
            continue
        lines.append(kind.upper() + ":")
        for m in names:
            tag = ""
            if kind == "image" and m == pick_model("image"):
                tag = " [auto image]"
            if kind == "video" and m == pick_model("video"):
                tag = " [auto video]"
            lines.append("  %s%s" % (m, tag))
    lines.append("")
    lines.append("Use a name in the model argument of generate_image/generate_video,")
    lines.append("or CRAYONBOX_IMAGE_MODEL/CRAYONBOX_VIDEO_MODEL to pin it.")
    return "\n".join(lines)


def find_url(obj):
    if isinstance(obj, dict):
        for k in ("url", "image_url", "video_url"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
        for v in obj.values():
            found = find_url(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_url(v)
            if found:
                return found
    return None


def target_path(path, kind, url=None):
    if path:
        return path
    ext = ".png" if kind == "image" else ".mp4"
    if url:
        suffix = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm"):
            ext = suffix
    folder = "generated-images" if kind == "image" else "generated-videos"
    return os.path.join(OUTPUT_DIR or os.getcwd(), folder, "%s-%d%s" % (kind, int(time.time()), ext))


def save(url, path, kind):
    path = target_path(path, kind, url)
    want = "image/" if kind == "image" else "video/"
    req = urllib.request.Request(url, headers={"User-Agent": "crayonbox/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            ctype = r.headers.get_content_type()
            if not ctype.startswith(want):
                raise ApiError("download %s returned %s, not %s: %s"
                               % (url, ctype, want + "*", r.read(800).decode(errors="replace")))
            data = r.read()
    except urllib.error.URLError as e:
        raise ApiError("cannot download %s: %s" % (url, e.reason)) from e
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def parse_task_id(resp):
    for k in ("video_id", "id", "task_id"):
        v = resp.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def poll_video(video_id, model):
    query = urllib.parse.urlencode({"video_id": video_id, "model_name": model})
    try:
        return api("%s/agnesapi?%s" % (ROOT, query))
    except ApiError as e:
        if e.status == 404:
            return api("/videos/" + urllib.parse.quote(video_id))
        raise


def wait_video(video_id, model, seconds=15):
    deadline = time.monotonic() + seconds
    resp = poll_video(video_id, model)
    while resp.get("status") not in DONE and resp.get("status") != "failed":
        if time.monotonic() >= deadline:
            break
        time.sleep(2)
        resp = poll_video(video_id, model)
    return resp


def image_body(args):
    ratio = args.get("ratio")
    if ratio and ratio not in RATIOS:
        raise ValueError("ratio must be one of " + ", ".join(sorted(RATIOS)))
    body = {"model": pick_model("image", args.get("model")), "prompt": args["prompt"]}
    size = args.get("size") or opt("CRAYONBOX_IMAGE_SIZE", "image_size", "1K")
    if size:
        body["size"] = size
    if ratio:
        body["ratio"] = ratio
    refs = args.get("reference_images") or []
    if refs:
        body["extra_body"] = {"image": refs}
    return body


def generate_image(args):
    body = image_body(args)
    resp = api("/images/generations", body)
    url = find_url(resp)
    if url:
        path = save(url, args.get("path"), "image")
        return "image saved to %s (model %s)\n%s" % (path, body["model"], url)
    item = (resp.get("data") or [{}])[0] if isinstance(resp.get("data"), list) else resp
    b64 = item.get("b64_json") or resp.get("b64_json")
    if b64:
        path = target_path(args.get("path"), "image")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        return "image saved to %s (model %s)" % (path, body["model"])
    raise ApiError("no image in reply: " + json.dumps(resp, ensure_ascii=False)[:800])


def video_body(args):
    seconds = int(args.get("seconds", 5))
    if not 1 <= seconds <= 30:
        raise ValueError("seconds must be 1-30")
    ratio = args.get("aspect_ratio", "16:9")
    if ratio not in RATIOS:
        raise ValueError("aspect_ratio must be one of " + ", ".join(sorted(RATIOS)))
    body = {
        "model": pick_model("video", args.get("model")),
        "prompt": args["prompt"],
        "mode": "text",
        "seconds": str(seconds),
        "aspect_ratio": ratio,
        "n": 1,
    }
    size = args.get("size") or opt("CRAYONBOX_VIDEO_SIZE", "video_size", "720P")
    if size:
        body["size"] = size
    first = args.get("first_frame")
    if first:
        body["mode"] = "keyframe"
        body["first_frame"] = first
    return body


def generate_video(args):
    body = video_body(args)
    resp = api("/videos", body)
    video_id = parse_task_id(resp)
    if not video_id:
        raise ApiError("no video id in reply: " + json.dumps(resp, ensure_ascii=False)[:800])
    final = wait_video(video_id, body["model"])
    if final.get("status") in DONE:
        url = find_url(final)
        if not url:
            raise ApiError("video finished without a url: " + json.dumps(final, ensure_ascii=False)[:800])
        path = save(url, args.get("path"), "video")
        return "video saved to %s (model %s)\n%s" % (path, body["model"], url)
    if final.get("status") == "failed":
        raise ApiError("video failed: " + json.dumps(final, ensure_ascii=False)[:800])
    return "still making video %s (model %s, status: %s); call generation_result with this id" % (
        video_id, body["model"], final.get("status"))


def generation_result(args):
    model = pick_model("video", args.get("model"))
    final = wait_video(args["id"], model)
    if final.get("status") in DONE:
        url = find_url(final)
        if not url:
            raise ApiError("video finished without a url: " + json.dumps(final, ensure_ascii=False)[:800])
        path = save(url, args.get("path"), "video")
        return "video saved to %s (model %s)\n%s" % (path, model, url)
    if final.get("status") == "failed":
        raise ApiError("video failed: " + json.dumps(final, ensure_ascii=False)[:800])
    return "video %s still making (status: %s); call generation_result again" % (
        args["id"], final.get("status"))


TOOLS = [
    {
        "name": "generate_image",
        "description": "Generate or edit an image with the configured provider. Picks the best image model from the "
                       "provider's model list unless one is named. Saves a file in the project (generated-images/ "
                       "unless path says where) and returns its path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "What to draw, or how to change the reference images."},
                "model": {"type": "string", "description": "Model id; skipped, one is picked from /models."},
                "size": {"type": "string", "description": "Provider size, e.g. 1K, 2K, 1024x1024. Default from env."},
                "ratio": {"type": "string", "enum": sorted(RATIOS), "description": "Aspect ratio when the provider takes one."},
                "reference_images": {"type": "array", "items": {"type": "string"},
                                     "description": "Public image URLs or data: URIs for edit/compose."},
                "path": {"type": "string", "description": "Where to save it, e.g. assets/hero.png"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_video",
        "description": "Generate a short video with the configured provider. Picks the best video model from the "
                       "provider's model list unless one is named. Saves an mp4 in the project (generated-videos/ "
                       "unless path says where); returns an id to poll with generation_result when it is not ready "
                       "within about 15 seconds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Subject, motion and camera."},
                "model": {"type": "string", "description": "Model id; skipped, one is picked from /models."},
                "seconds": {"type": "integer", "minimum": 1, "maximum": 30, "default": 5},
                "aspect_ratio": {"type": "string", "enum": sorted(RATIOS), "default": "16:9"},
                "size": {"type": "string", "description": "Provider size, e.g. 720P. Default from env."},
                "first_frame": {"type": "string", "description": "Optional public image URL for keyframe mode."},
                "path": {"type": "string", "description": "Where to save the mp4."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "list_models",
        "description": "List the provider's models grouped as IMAGE / VIDEO / CHAT / OTHER, "
                       "with the models auto-picked when no model is named. "
                       "Use it before asking which model to use.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "generation_result",
        "description": "Check a video started by generate_video, by the id it returned, and save it when ready.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The id generate_video returned."},
                "model": {"type": "string", "description": "The model used; picked from /models when omitted."},
                "path": {"type": "string", "description": "Where to save the mp4."},
            },
            "required": ["id"],
        },
    },
]


def call_tool(name, args):
    if not KEY:
        raise ApiError("no API key: set CRAYONBOX_API_KEY or api_key in ~/.config/crayonbox.json")
    if name == "generate_image":
        return generate_image(args)
    if name == "generate_video":
        return generate_video(args)
    if name == "generation_result":
        return generation_result(args)
    if name == "list_models":
        return list_models()
    raise ValueError("unknown tool: " + name)


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(method, params):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "crayonbox", "version": "1.0.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        try:
            text = call_tool(params.get("name"), params.get("arguments") or {})
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    if method == "ping":
        return {}
    raise ValueError("unknown method: " + method)


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg or "method" not in msg:
            continue
        try:
            send({"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg["method"], msg.get("params") or {})})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": msg["id"],
                  "error": {"code": -32603, "message": str(e)}})


def selftest():
    assert find_url({"metadata": {"url": "https://x/v.mp4"}}) == "https://x/v.mp4"
    assert find_url({"data": [{"url": "https://x/i.png"}]}) == "https://x/i.png"
    assert find_url({"status": "queued"}) is None
    assert parse_task_id({"video_id": "v1", "id": "t1"}) == "v1"
    assert version_key("agnes-video-2.5-flash") == (2, 5)
    _cache.update(at=time.time(), ids=[
        "agnes-3.0-flash", "agnes-image-2.5-flash", "agnes-video-2.5", "agnes-video-2.5-flash",
        "text-embedding-3"])
    assert pick_model("image") == "agnes-image-2.5-flash"
    assert pick_model("video") == "agnes-video-2.5-flash"
    ib = image_body({"prompt": "p", "reference_images": ["https://x/i.png"]})
    assert ib["extra_body"] == {"image": ["https://x/i.png"]}
    assert ib["size"] == "1K" and "ratio" not in ib
    vb = video_body({"prompt": "p"})
    assert vb["seconds"] == "5" and vb["size"] == "720P" and vb["mode"] == "text"
    print("selftest ok")


def setup():
    global BASE, ROOT, KEY, CFG
    cfg = _load_config()
    default = cfg.get("base_url", "")
    base = input("Base URL" + (" [%s]" % default if default else "") + ": ").strip() or default
    if not base:
        raise SystemExit("a base URL is required, e.g. https://api.example.com/v1")
    hint = " [keep current]" if cfg.get("api_key") else ""
    key = getpass.getpass("API key%s: " % hint).strip() or cfg.get("api_key", "")
    if not key:
        raise SystemExit("an API key is required")
    cfg["base_url"] = base.rstrip("/")
    cfg["api_key"] = key
    folder = os.path.dirname(CONFIG_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.chmod(CONFIG_PATH, 0o600)
    print("saved %s" % CONFIG_PATH)
    BASE, KEY, CFG = cfg["base_url"], key, cfg
    ROOT = BASE[:-3] if BASE.endswith("/v1") else BASE
    _cache.update(at=0.0, ids=[])
    try:
        ids = model_ids()
    except ApiError as e:
        print("warning: could not list models yet: %s" % e)
        return
    print("models: " + ", ".join(ids))
    print("image: %s" % pick_model("image"))
    print("video: %s" % pick_model("video"))


def cli(argv):
    cmd, rest = (argv[0] if argv else "serve"), argv[1:]
    if cmd == "setup":
        setup()
        return
    if cmd == "set":
        if not rest or any("=" not in a for a in rest):
            raise SystemExit("usage: crayonbox set base_url=https://… api_key=sk-… [image_size=1K]")
        cfg = _load_config()
        for item in rest:
            k, v = item.split("=", 1)
            cfg[k.strip()] = v
        folder = os.path.dirname(CONFIG_PATH)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.chmod(CONFIG_PATH, 0o600)
        print("saved %s: %s" % (CONFIG_PATH, ", ".join(sorted(cfg))))
        return
    if cmd == "show":
        cfg = dict(CFG)
        for k in list(cfg):
            if k == "api_key" and cfg[k]:
                cfg[k] = cfg[k][:4] + "…" + cfg[k][-4:]
        print(CONFIG_PATH)
        print(json.dumps(cfg, ensure_ascii=False, indent=2) if cfg else "(empty)")
        return
    if cmd == "models":
        print("\n".join(model_ids()))
        return
    if cmd in ("serve", "-s"):
        serve()
        return
    if cmd in ("-h", "--help", "help"):
        print("usage: crayonbox [setup|serve|set k=v…|show|models|--selftest]")
        return
    raise SystemExit("unknown command: " + cmd)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        cli(sys.argv[1:])
