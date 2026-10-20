# CrayonBox

Image and video generation for any agent. One stdio MCP server, one shared config,
any OpenAI-compatible provider — bring your own base URL and key, models are
picked from the provider's `/models` list.

Works wherever MCP speaks stdio: Claude Code, Claude Desktop, ChatGPT Desktop,
Qoder, Codex, Cursor, Gemini CLI, and any other client.

## Requirements

- macOS or Linux, Python 3.9+ (stdlib only, no dependencies, nothing to install)

## One-time setup

Clone once, then configure once — every agent reads the same file:

```bash
git clone https://github.com/HPygmalion/crayonbox
/path/to/crayonbox/scripts/crayonbox.py setup
```

`setup` asks for the base URL, then the API key with hidden input, writes
`~/.config/crayonbox.json` (mode 600) and prints the models it found.
This is the only configuration step any agent needs — they all read that file,
so no environment variables go into any agent's config.

The Claude plugin's install form is optional; when filled it wins over the file
for Claude only. Everything else keeps using the shared file.

## Install per agent

### Claude Code / Claude Desktop (plugin: skills + config UI)

```bash
claude plugin marketplace add HPygmalion/crayonbox
claude plugin install crayonbox@crayonbox
```

Optionally fill the install form (base URL, API key, models); skip it to use
the shared config. Skills: `/generate-image`, `/generate-video`,
`/generation-result` — Claude-only, other agents get the same four MCP tools.

### Claude Code (plain MCP, no plugin)

```bash
claude mcp add crayonbox -- python3 /path/to/crayonbox/scripts/crayonbox.py
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "crayonbox": {
      "command": "python3",
      "args": ["/path/to/crayonbox/scripts/crayonbox.py"]
    }
  }
}
```

### ChatGPT Desktop

Settings → **MCP servers** → **Add server** → type **STDIO**:

```
Command: python3 /path/to/crayonbox/scripts/crayonbox.py
```

(Requires developer mode. Local stdio only works in the desktop app, not the web app.)

### Qoder / Cursor / Windsurf / other MCP clients

Add a stdio server named `crayonbox`:

```json
{
  "mcpServers": {
    "crayonbox": {
      "command": "python3",
      "args": ["/path/to/crayonbox/scripts/crayonbox.py"]
    }
  }
}
```

### Codex

```toml
[mcp_servers.crayonbox]
command = "python3"
args = ["/path/to/crayonbox/scripts/crayonbox.py"]
```

## Tools

- `generate_image` — text-to-image, image-to-image, multi-image compose;
  saves to `generated-images/` unless `path` says where
- `generate_video` — text-to-video or keyframe; saves mp4 to `generated-videos/`;
  returns a task id when the job outlives ~15 s
- `generation_result` — poll a video task id started by `generate_video`
- `list_models` — provider models grouped as IMAGE / VIDEO / CHAT / OTHER,
  with the auto-picked models marked

## CLI

```bash
crayonbox setup        # interactive: base URL, then hidden key input
crayonbox set k=v …    # non-interactive
crayonbox show         # key masked
crayonbox models       # list model ids
crayonbox serve        # run the MCP server (what agents call)
```

Config lives in `~/.config/crayonbox.json` (mode 600). Environment variables
`CRAYONBOX_BASE_URL`, `CRAYONBOX_API_KEY`, `CRAYONBOX_IMAGE_MODEL`,
`CRAYONBOX_VIDEO_MODEL`, `CRAYONBOX_IMAGE_SIZE`, `CRAYONBOX_VIDEO_SIZE`,
`CRAYONBOX_OUTPUT_DIR` win over the file.

## Model auto-pick rule

Candidates are matched by name (`image/imagen/flux/…`, `video/veo/sora/kling/…`),
then the highest version wins, ties preferring `flash` variants. Pass `model`
per call, or set `CRAYONBOX_IMAGE_MODEL` / `CRAYONBOX_VIDEO_MODEL` to pin.

## Provider shape (verified: Agnes)

- `GET /models` — OpenAI shape
- `POST /images/generations` — `size` (`1K`/`2K`/…) + optional `ratio`;
  reference images go in `extra_body.image`
- `POST /videos` — `mode`, `seconds` as a string, `size` (`720P`),
  `aspect_ratio`; polled via provider-specific query endpoint with fallback
  to `GET /videos/<id>`

Other OpenAI-compatible endpoints work as long as they follow the same shape.
Pure-OpenAI endpoints that reject extras like `extra_body` or `ratio` are not
currently supported.
