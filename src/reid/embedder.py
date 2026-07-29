"""
Embedder trích xuất vector ReID từ crop người.

File này bọc OSNet-AIN checkpoint hiện có. Runtime chỉ import/load embedder khi
`enable_reid=True`, tránh kéo torch/torchreid trong luồng detect-only.
"""

from __future__ import annotations

from collections import OrderedDict
import gc
from pathlib import Path
from typing import Literal, Sequence, Union

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import Tensor, nn
from torchreid.reid.models import build_model
from torchvision import transforms
from src.model_catalog import find_default_model, resolve_model_path


ImageInput = Union[str, Path, Image.Image, np.ndarray]
ColorFormat = Literal["rgb", "bgr"]


# ─────────────────────────────────────────────────────────────────────────────
class OSNetPersonEmbedder:
    """
    Trích xuất embedding người bằng OSNet-AIN.

    Input nên là crop người BGR/RGB. Output luôn được L2-normalize để so cosine.
    """

    model_name = "osnet_ain_x1_0"
    embedding_dim = 512
    input_size = (256, 128)
    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        device: str | torch.device = "auto",
        batch_size: int = 32,
        verbose: bool = False,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        if model_path is None:
            default_model_id = find_default_model("reid")
            if default_model_id is None:
                raise FileNotFoundError("Không tìm thấy ReID model trong weights.")
            model_path = resolve_model_path(default_model_id, kind="reid")

        self.model_path = Path(model_path)
        self.device = self._pick_device(device)
        self.batch_size = batch_size
        self.transform = self._build_preprocess()
        self.model = self._load_model(verbose=verbose)

    def close(self) -> None:
        """Release model references and cached accelerator memory."""
        try:
            model = getattr(self, "model", None)
            if model is not None:
                try:
                    model.to("cpu")
                except Exception:
                    pass
                self.model = None
        finally:
            gc.collect()

            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                except Exception:
                    pass

            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                try:
                    torch.mps.empty_cache()
                except Exception:
                    pass

    def extract_embedding(
        self,
        image: ImageInput,
        *,
        color_format: ColorFormat = "rgb",
    ) -> Tensor:
        """Extract một normalized embedding shape [512]."""
        return self.extract_embeddings([image], color_format=color_format)[0]

    @torch.inference_mode()
    def extract_embeddings(
        self,
        images: Sequence[ImageInput],
        *,
        color_format: ColorFormat = "rgb",
        batch_size: int | None = None,
    ) -> Tensor:
        """Extract normalized embeddings shape [N, 512]."""
        if not images:
            raise ValueError("images must not be empty")

        actual_batch_size = batch_size or self.batch_size
        if actual_batch_size <= 0:
            raise ValueError("batch_size must be positive")

        if self.model is None:
            raise RuntimeError("ReID embedder is closed.")

        outputs: list[Tensor] = []
        for start in range(0, len(images), actual_batch_size):
            chunk = images[start : start + actual_batch_size]
            batch = torch.stack(
                [self._preprocess_image(image, color_format) for image in chunk],
                dim=0,
            ).to(self.device)
            features = self.model(batch)
            features = F.normalize(features, p=2, dim=1)
            outputs.append(features.cpu())

        return torch.cat(outputs, dim=0)

    def _load_model(self, *, verbose: bool) -> nn.Module:
        """Load OSNet model và nạp checkpoint tương thích."""
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Missing ReID weights: {self.model_path}")

        model = build_model(
            name=self.model_name,
            num_classes=1,
            loss="softmax",
            pretrained=False,
            use_gpu=self.device.type == "cuda",
        )

        model_state = model.state_dict()
        pretrained_state = self._load_state_dict(self.model_path)
        matched: dict[str, Tensor] = {}
        discarded: list[str] = []

        for key, value in pretrained_state.items():
            if key in model_state and model_state[key].shape == value.shape:
                matched[key] = value
            else:
                discarded.append(key)

        if not matched:
            raise RuntimeError(f"No compatible layers found in {self.model_path}")

        model_state.update(matched)
        model.load_state_dict(model_state)
        model.eval().to(self.device)

        if verbose:
            print(f"Loaded {len(matched)} ReID layers from {self.model_path}")
            if discarded:
                print(f"Discarded {len(discarded)} incompatible ReID layers.")

        return model

    @staticmethod
    def _load_state_dict(weight_path: Path) -> OrderedDict[str, Tensor]:
        """Đọc checkpoint torchreid và bỏ prefix module nếu có."""
        checkpoint = torch.load(weight_path, map_location="cpu", weights_only=False)
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            checkpoint = checkpoint["state_dict"]
        if not isinstance(checkpoint, dict):
            raise TypeError(f"Unsupported checkpoint type: {type(checkpoint)!r}")

        state_dict: OrderedDict[str, Tensor] = OrderedDict()
        for key, value in checkpoint.items():
            if isinstance(value, Tensor):
                state_dict[key.removeprefix("module.")] = value

        return state_dict

    @classmethod
    def _build_preprocess(cls) -> transforms.Compose:
        """Preprocess theo input chuẩn của OSNet."""
        return transforms.Compose(
            [
                transforms.Resize(cls.input_size),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def _preprocess_image(self, image: ImageInput, color_format: ColorFormat) -> Tensor:
        """Chuyển input image sang tensor model-ready."""
        return self.transform(self._to_pil_image(image, color_format))

    @staticmethod
    def _to_pil_image(image: ImageInput, color_format: ColorFormat) -> Image.Image:
        """Chuẩn hóa input thành PIL RGB."""
        if isinstance(image, (str, Path)):
            return Image.open(image).convert("RGB")
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        if isinstance(image, np.ndarray):
            if image.ndim != 3 or image.shape[2] != 3:
                raise ValueError(f"Expected numpy image shape [H, W, 3], got {image.shape}")
            array = image[:, :, ::-1] if color_format == "bgr" else image
            return Image.fromarray(array.astype(np.uint8)).convert("RGB")

        raise TypeError(f"Unsupported image input type: {type(image)!r}")

    @staticmethod
    def _pick_device(device: str | torch.device) -> torch.device:
        """Chọn device chạy ReID."""
        if isinstance(device, torch.device):
            return device
        if device != "auto":
            return torch.device(device)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")

        return torch.device("cpu")
