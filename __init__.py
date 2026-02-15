from .video_fps_chunker import VideoFPSChunkerExtension

async def comfy_entrypoint() -> VideoFPSChunkerExtension:
    return VideoFPSChunkerExtension()
