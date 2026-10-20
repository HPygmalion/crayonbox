---
name: generation-result
description: Check a video started by generate-video and save it when ready. Use when a generate-video call returned a task id, or the user asks whether a video is done.
---

# generation-result

Use the bundled MCP tool `generation_result` when it is available:

- `id` — the id `generate_video` returned
- `model` — the model used; omit to pick again from the provider's model list
- `path` — where to save the mp4

A reply that says the video is still being made means: call again later with the same id. Do not start a new generation.
