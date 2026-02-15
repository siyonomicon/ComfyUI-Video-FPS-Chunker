# Video Processing Nodes

ComfyUI custom nodes for video processing, including video chunking and batch video loading.

## Nodes

### 1. Video Chunker

Splits videos into exact frame chunks while preserving original FPS.

**Features:**
- Splits video into chunks with configurable frame count (default: 77 frames)
- Guarantees exact frame count per chunk (except last chunk)
- Preserves original FPS
- Correct duration metadata (no frozen frames when playing)
- High quality re-encoding (CRF 18 - visually lossless)
- Preserves audio without re-encoding
- Organizes chunks by video hash to avoid conflicts
- Uses system ffmpeg or imageio-ffmpeg

**How It Works:**
1. Gets total frame count and FPS from input video
2. Calculates number of chunks needed
3. Extracts each chunk using time-based seeking with frame limiting
4. Properly updates duration metadata for correct playback

**Inputs:**
- `video`: Video input to process
- `output_dir`: Base output directory name (default: "video_chunks")
- `frames_per_chunk`: Number of frames per chunk (default: 77, range: 1-10000)

**Outputs:**
- `chunk_dir_path`: Absolute path to the directory containing chunks
- `total_chunks`: Total number of chunks created

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

### 3. Int to String

Simple utility node that converts an integer to a string.

**Features:**
- Converts integer values to string format
- Useful for connecting integer outputs to string inputs
- Simple pass-through conversion

**Inputs:**
- `value`: Integer value to convert

**Outputs:**
- `string`: String representation of the integer

**Use Cases:**
- Connect `total_chunks` output from Video Chunker to string-based nodes
- Convert frame counts, indices, chunk counts, or other numeric values to text
- Build dynamic file paths or labels with numeric components

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
LoadVideoBatch → VideoChunker
```

1. LoadVideoBatch loads videos one by one from a directory
2. VideoChunker splits each video into 77-frame chunks (preserving original FPS)
3. Each execution processes the next video automatically

### Example 2: Batch process with custom chunk size

```
LoadVideoBatch (path="/videos", pattern="*.mp4", label="MyBatch")
  ↓
VideoChunker (frames_per_chunk=60)
```

This will:
- Load videos from `/videos` directory (only .mp4 files)
- Track progress with label "MyBatch"
- Split each video into 60-frame chunks (preserving original FPS and quality)
- Automatically move to next video on each run

## Video Chunker Details

**How It Works:**
1. Counts total frames in the input video using ffprobe
2. Gets video FPS for accurate time-based seeking
3. Calculates number of chunks needed
4. Extracts each chunk using `-ss` (seek) and `-frames:v` (frame limit)
5. Properly updates duration metadata for correct playback
6. Returns chunk directory path and total frame count

**Technical Details:**
- Uses ffmpeg time-based seeking: `-ss <start_time>`
- Frame limiting: `-frames:v <count>`
- Re-encodes with libx264 CRF 18 (visually lossless quality)
- Audio encoded with AAC at 192kbps
- Preserves original FPS
- Frame-accurate extraction guaranteed
- Correct duration metadata (no frozen frames)

**Example Output:**

Input: 524 frames video @ 30 FPS, frames_per_chunk=77
- Output: 7 chunks
  - 0.mp4: 77 frames (2.57s) ✓
  - 1.mp4: 77 frames (2.57s) ✓
  - 2.mp4: 77 frames (2.57s) ✓
  - 3.mp4: 77 frames (2.57s) ✓
  - 4.mp4: 77 frames (2.57s) ✓
  - 5.mp4: 77 frames (2.57s) ✓
  - 6.mp4: 62 frames (2.07s) ✓ (last chunk)
- Total chunks output: 7

Input: 240 frames video @ 24 FPS, frames_per_chunk=60
- Output: 4 chunks
  - Each chunk: exactly 60 frames (2.5s at 24 FPS)
- Total chunks output: 4

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
