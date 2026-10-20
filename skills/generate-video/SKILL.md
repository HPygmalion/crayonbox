---
name: generate-video
description: Generate a short video (text-to-video, or keyframe from a first frame) with the user's configured video model. Use when the user asks to make, animate, or create a video or clip.
---

# generate-video

Use the bundled MCP tool `generate_video` when it is available:

- `prompt` — subject, motion, camera
- `seconds` — 1–30, default 5
- `aspect_ratio` — default `16:9`
- `first_frame` — optional public image URL for keyframe mode
- `model` — omit to auto-pick from the provider's model list
- `path` — where to save the mp4; omit to use `generated-videos/`

When the tool returns a task id instead of a file, the generation is still running: use the `generation-result` skill with that id.

## When the tool is missing

Tell the user to enable the crayonbox plugin and fill base URL and API key in the plugin's configuration, then reload. Do not ask for the key in chat.
