# Video Processing Nodes

ComfyUI custom nodes for video processing, including FPS reduction/chunking and batch video loading.

## Nodes

### 1. Video FPS Chunker

Processes videos by reducing FPS to 16 (by stretching duration, not dropping frames) and splitting them into configurable frame chunks.

**Features:**
- Reduces video FPS to 16 by stretching duration (no frames are lost)
- Splits video into chunks with configurable frame count (default: 77 frames)
- Saves each chunk as a separate MP4 file
- Organizes chunks by video hash to avoid conflicts
- Uses system ffmpeg or imageio-ffmpeg

**Inputs:**
- `video`: Video input to process
- `output_dir`: Base output directory name (default: "video_chunks")
- `frames_per_chunk`: Number of frames per chunk (default: 77, range: 1-10000)

**Outputs:**
- `chunk_dir_path`: Absolute path to the directory containing chunks

**Output Structure:**
```
{ComfyUI_output_dir}/
└── {output_dir}/
    └── {video_hash}/
        ├── 0.mp4
        ├── 1.mp4
        ├── 2.mp4
        └── ...
```

### 2. Load Video Batch

Load videos from a directory in incremental mode, automatically tracking which video was last processed.

**Features:**
- Incremental video loading (automatically moves to next video)
- Persistent state tracking across sessions
- Supports glob patterns for filtering
- Resets counter when path or pattern changes
- Never processes the same video twice in sequence

**Inputs:**
- `path`: Directory path containing videos
- `pattern`: Glob pattern to filter videos (default: "*", e.g., "*.mp4")
- `label`: Unique label to track this batch's progress (default: "Batch 001")
- `index`: Manual index override (currently not used in incremental mode)

**Outputs:**
- `video`: Loaded video
- `filename`: Video filename
- `current_index`: Current video index (0-based)
- `total_videos`: Total number of videos in batch

**How It Works:**
1. Scans directory for videos matching the pattern
2. Loads state from JSON database (stored in ComfyUI output directory)
3. Returns the next video in sequence
4. Saves updated index for next execution
5. Automatically loops back to start when reaching the end

**State Tracking:**
- State is stored in `{ComfyUI_output_dir}/video_batch_state.json`
- Each label maintains its own counter, path, and pattern
- Counter resets automatically if path or pattern changes
- State persists across ComfyUI restarts

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

## Usage Examples

### Example 1: Process videos incrementally

```
LoadVideoBatch → VideoFPSChunker
```

1. LoadVideoBatch loads videos one by one from a directory
2. VideoFPSChunker processes each video into 77-frame chunks at 16 FPS
3. Each execution processes the next video automatically

### Example 2: Batch process with custom chunk size

```
LoadVideoBatch (path="/videos", pattern="*.mp4", label="MyBatch")
  ↓
VideoFPSChunker (frames_per_chunk=60)
```

This will:
- Load videos from `/videos` directory (only .mp4 files)
- Track progress with label "MyBatch"
- Split each video into 60-frame chunks at 16 FPS
- Automatically move to next video on each run

## Video FPS Chunker Details

**How It Works:**
1. Calculates SHA256 hash of input video (first 16 chars used)
2. Stretches video duration using `setpts` filter to achieve 16 FPS
3. Re-encodes video with libx264 at 16 FPS
4. Splits into chunks using ffmpeg segment muxer
5. Returns realpath of the directory containing chunks

**Example Output:**

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

## Supported Video Formats

- .mp4
- .avi
- .mov
- .mkv
- .webm
- .flv
- .wmv
- .m4v
- .mpg
- .mpeg
