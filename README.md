# Video FPS Chunker

A ComfyUI custom node that processes videos by reducing FPS to 16 (by stretching duration, not dropping frames) and splitting them into configurable frame chunks.

## Features

- Reduces video FPS to 16 by stretching duration (no frames are lost)
- Splits video into chunks with configurable frame count (default: 77 frames)
- Saves each chunk as a separate MP4 file
- Organizes chunks by video hash to avoid conflicts
- Uses system ffmpeg or imageio-ffmpeg

## Requirements

- ffmpeg installed on system, OR
- `imageio-ffmpeg` Python package

Install ffmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Or install imageio-ffmpeg
pip install imageio-ffmpeg
```

## Usage

1. Add the "Video FPS Chunker" node to your workflow
2. Connect a video input (from LoadVideo or other video source)
3. Set the output directory name (default: "video_chunks")
4. Set frames per chunk (default: 77, range: 1-10000)
5. Run the workflow

## Output Structure

```
{ComfyUI_output_dir}/
└── {output_dir}/
    └── {video_hash}/
        ├── 0.mp4
        ├── 1.mp4
        ├── 2.mp4
        └── ...
```

The node returns the absolute path to the chunk directory.

## How It Works

1. Calculates SHA256 hash of input video (first 16 chars used)
2. Stretches video duration using `setpts` filter to achieve 16 FPS
3. Re-encodes video with libx264 at 16 FPS
4. Splits into chunks using ffmpeg segment muxer
5. Returns realpath of the directory containing chunks

## Example

Input: 30 FPS video with 231 frames, frames_per_chunk=77
- Duration is stretched from ~7.7s to ~14.4s
- Output: 3 chunks (0.mp4, 1.mp4, 2.mp4)
  - 0.mp4: frames 0-76 (4.8125s)
  - 1.mp4: frames 77-153 (4.8125s)
  - 2.mp4: frames 154-230 (4.8125s)

Input: 24 FPS video with 240 frames, frames_per_chunk=60
- Duration is stretched from ~10s to ~15s
- Output: 4 chunks (0.mp4, 1.mp4, 2.mp4, 3.mp4)
  - Each chunk: 60 frames (3.75s at 16 FPS)
