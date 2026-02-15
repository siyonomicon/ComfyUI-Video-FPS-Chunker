from __future__ import annotations

import os
import hashlib
import subprocess
import shutil
import tempfile
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, Input
import folder_paths


# Import processed videos database
from .check_video_processed import PROCESSED_DB


class VideoFPSChunker(io.ComfyNode):
    """
    Splits video into configurable frame chunks saved as separate MP4 files.
    Preserves original FPS and frames.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VideoFPSChunker",
            display_name="Video Chunker",
            category="video/processing",
            description="Split video into frame chunks (preserves original FPS)",
            inputs=[
                io.Video.Input("video", tooltip="The video to process"),
                io.String.Input(
                    "output_dir",
                    default="video_chunks",
                    tooltip="Base output directory name"
                ),
                io.Int.Input(
                    "frames_per_chunk",
                    default=77,
                    min=1,
                    max=10000,
                    step=1,
                    tooltip="Number of frames per chunk"
                ),
            ],
            outputs=[
                io.String.Output(display_name="chunk_dir_path"),
                io.Int.Output(display_name="total_chunks"),
            ],
        )

    @classmethod
    def get_ffmpeg_path(cls):
        """Get ffmpeg binary path, prefer system installation over imageio-ffmpeg"""
        # Try system ffmpeg first
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg

        # Try imageio-ffmpeg
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

        raise RuntimeError("ffmpeg not found. Install ffmpeg or imageio-ffmpeg package.")

    @classmethod
    def calculate_video_hash(cls, video_path: str) -> str:
        """Calculate SHA256 hash of video file"""
        sha256_hash = hashlib.sha256()
        with open(video_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()[:16]  # Use first 16 chars for shorter names

    @classmethod
    def get_video_frame_count(cls, ffmpeg_path: str, video_path: str) -> int:
        """Get total frame count using ffprobe"""
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-count_frames",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames",
            "-of", "default=nokey=1:noprint_wrappers=1",
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return int(result.stdout.strip())

    @classmethod
    def get_video_fps(cls, ffmpeg_path: str, video_path: str) -> float:
        """Get video FPS using ffprobe"""
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        fps_str = result.stdout.strip()

        # Parse frame rate
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den
        else:
            fps = float(fps_str)

        return fps

    @classmethod
    def execute(cls, video: Input.Video, output_dir: str, frames_per_chunk: int) -> io.NodeOutput:
        # Get video source
        video_source = video.get_stream_source()

        # Handle both file path and BytesIO
        temp_video_path = None
        cleanup_temp = False

        if isinstance(video_source, str):
            video_path = video_source
        else:
            # BytesIO - save to temporary file
            temp_dir = tempfile.mkdtemp()
            temp_video_path = os.path.join(temp_dir, "input_video.mp4")
            with open(temp_video_path, "wb") as f:
                video_source.seek(0)
                f.write(video_source.read())
            video_path = temp_video_path
            cleanup_temp = True

        try:
            # Get ffmpeg path
            try:
                ffmpeg_path = cls.get_ffmpeg_path()
            except RuntimeError as e:
                raise RuntimeError(f"FFmpeg not found: {e}")

            # Calculate video hash
            video_hash = cls.calculate_video_hash(video_path)

            # Create output directory structure
            output_base = folder_paths.get_output_directory()
            chunk_base_dir = os.path.join(output_base, output_dir, video_hash)

            # Check if video was already processed AND chunks still exist
            if PROCESSED_DB.is_processed(video_hash):
                existing_chunk_dir = PROCESSED_DB.get_chunk_dir(video_hash)

                # Verify chunks actually exist
                if os.path.exists(existing_chunk_dir) and os.path.isdir(existing_chunk_dir):
                    existing_chunks = sorted([f for f in os.listdir(existing_chunk_dir) if f.endswith('.mp4')])
                    if len(existing_chunks) > 0:
                        print(f"Video already processed, using existing chunks: {existing_chunk_dir} ({len(existing_chunks)} chunks)")
                        return io.NodeOutput(os.path.realpath(existing_chunk_dir), len(existing_chunks))
                    else:
                        print(f"Chunks directory exists but empty, re-processing: {existing_chunk_dir}")
                else:
                    print(f"Chunks were deleted, re-processing video (hash: {video_hash})")

                # Chunks don't exist - remove stale entry and continue processing
                if video_hash in PROCESSED_DB.data:
                    del PROCESSED_DB.data[video_hash]
                    PROCESSED_DB.save()

            # Continue with normal processing
            os.makedirs(chunk_base_dir, exist_ok=True)

            # Get total frame count and FPS
            try:
                total_frames = cls.get_video_frame_count(ffmpeg_path, video_path)
                fps = cls.get_video_fps(ffmpeg_path, video_path)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to get video info: {e.stderr}")

            # Calculate number of chunks
            num_chunks = (total_frames + frames_per_chunk - 1) // frames_per_chunk

            print(f"Processing video: {total_frames} frames @ {fps:.2f} FPS -> {num_chunks} chunks of {frames_per_chunk} frames")

            # Extract each chunk with time-based seeking and frame limiting
            for chunk_idx in range(num_chunks):
                start_frame = chunk_idx * frames_per_chunk
                num_frames_in_chunk = min(frames_per_chunk, total_frames - start_frame)
                start_time = start_frame / fps

                chunk_output = os.path.join(chunk_base_dir, f"{chunk_idx}.mp4")

                # Use time-based seeking with frame limiting for proper duration metadata
                cmd_extract = [
                    ffmpeg_path,
                    "-ss", str(start_time),  # Seek to start time
                    "-i", video_path,
                    "-frames:v", str(num_frames_in_chunk),  # Extract exact number of frames
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "18",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-y",
                    chunk_output
                ]

                try:
                    subprocess.run(cmd_extract, check=True, capture_output=True, text=True)
                    print(f"  Chunk {chunk_idx}: {num_frames_in_chunk} frames (starting at {start_time:.3f}s)")
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"Failed to extract chunk {chunk_idx}: {e.stderr}")

            # Verify chunks were created
            chunks = sorted([f for f in os.listdir(chunk_base_dir) if f.endswith('.mp4')])
            if not chunks:
                raise RuntimeError("No chunks were created. Video might be too short or invalid.")

            # Return absolute path to chunk directory and total chunks
            chunk_dir_realpath = os.path.realpath(chunk_base_dir)

            # Mark video as processed in database
            PROCESSED_DB.mark_processed(video_hash, chunk_dir_realpath)

            print(f"Video processed successfully: {len(chunks)} chunks created in {chunk_dir_realpath}")

            return io.NodeOutput(chunk_dir_realpath, num_chunks)

        finally:
            # Clean up temporary video if created
            if cleanup_temp and temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
                os.rmdir(os.path.dirname(temp_video_path))


class IntToString(io.ComfyNode):
    """
    Converts an integer to a string.
    Useful for connecting integer outputs to string inputs.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="IntToString",
            display_name="Int to String",
            category="utils",
            description="Convert integer to string",
            inputs=[
                io.Int.Input("value", tooltip="Integer value to convert"),
            ],
            outputs=[
                io.String.Output(display_name="string"),
            ],
        )

    @classmethod
    def execute(cls, value: int) -> io.NodeOutput:
        return io.NodeOutput(str(value))


class VideoFPSChunkerExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            VideoFPSChunker,
            IntToString,
        ]
