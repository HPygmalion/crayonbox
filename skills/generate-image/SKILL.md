---
name: generate-image
description: Generate or edit an image with the user's configured image model (text-to-image, image-to-image, multi-image compose). Use when the user asks to draw, generate, edit, or combine images.
---

# generate-image

Use the bundled MCP tool `generate_image` when it is available:

- `prompt` — what to draw, or how to change the reference images
- `size` — e.g. `1K`, `2K`; omit to use the server default
- `ratio` — `1:1`, `16:9`, …; omit if the provider takes none
- `reference_images` — public image URLs or data: URIs for edit/compose
- `model` — omit to auto-pick from the provider's model list
- `path` — where to save it; omit to use `generated-images/`

## When the tool is missing

Tell the user to enable the crayonbox plugin and fill base URL and API key in the plugin's configuration, then reload. Do not ask for the key in chat.
