from .video_fps_chunker import VideoFPSChunkerExtension
from .load_video_batch import LoadVideoBatchExtension
from .check_video_processed import CheckVideoProcessedExtension
from .video_info import VideoInfoExtension
from comfy_api.latest import ComfyExtension, io
from typing_extensions import override


class VideoProcessingExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        chunker_ext = VideoFPSChunkerExtension()
        batch_ext = LoadVideoBatchExtension()
        check_ext = CheckVideoProcessedExtension()
        info_ext = VideoInfoExtension()

        chunker_nodes = await chunker_ext.get_node_list()
        batch_nodes = await batch_ext.get_node_list()
        check_nodes = await check_ext.get_node_list()
        info_nodes = await info_ext.get_node_list()

        return chunker_nodes + batch_nodes + check_nodes + info_nodes


async def comfy_entrypoint() -> VideoProcessingExtension:
    return VideoProcessingExtension()
