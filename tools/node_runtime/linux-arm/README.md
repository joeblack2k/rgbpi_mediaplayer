Bundled Node.js runtime for Linux ARM should be placed here as:

node

Requirements:
- Linux ARM compatible executable
- executable bit set (`chmod +x node`)

Runtime resolution order:
1. `DVDPLAYER_YOUTUBE_NODE_BIN` override
2. this bundled binary (`tools/node_runtime/linux-arm/node`)
3. system `node` in `PATH` (development fallback)
