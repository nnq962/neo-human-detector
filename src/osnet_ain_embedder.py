from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Literal, Sequence, Union

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import Tensor, nn
from torchreid.reid.models import build_model
from torchvision import transforms


ImageInput = Union[str, Path, Image.Image, np.ndarray]
ColorFormat = Literal["rgb", "bgr"]


class OSNetAINEmbedder:
    """Embedding extractor for the OSNet-AIN MS+D+C checkpoint.

    Inputs should be cropped person images. Returned embeddings are always
    L2-normalized so they can be compared directly with cosine similarity.
    """

    model_name = "osnet_ain_x1_0"
    embedding_dim = 512
    input_size = (256, 128)
    default_weights = (
        Path(__file__).resolve().parents[1] / "weights" / "osnet_ain_ms_d_c.pth.tar"
    )

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

        self.model_path = Path(model_path) if model_path else self.default_weights
        self.device = self._pick_device(device)
        self.batch_size = batch_size
        self.transform = self._build_preprocess()
        self.model = self._load_model(verbose=verbose)

    def extract_embedding(
        self,
        image: ImageInput,
        *,
        color_format: ColorFormat = "rgb",
    ) -> Tensor:
        """Extract one normalized embedding with shape [512]."""

        return self.extract_embeddings([image], color_format=color_format)[0]

    @torch.inference_mode()
    def extract_embeddings(
        self,
        images: Sequence[ImageInput],
        *,
        color_format: ColorFormat = "rgb",
        batch_size: int | None = None,
    ) -> Tensor:
        """Extract normalized embeddings with shape [N, 512]."""

        if not images:
            raise ValueError("images must not be empty")

        actual_batch_size = batch_size or self.batch_size
        if actual_batch_size <= 0:
            raise ValueError("batch_size must be positive")

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

    @staticmethod
    def cosine_similarity(query: Tensor, gallery: Tensor) -> Tensor:
        """Compute cosine similarity for normalized or raw embedding tensors."""

        query_2d = query.unsqueeze(0) if query.ndim == 1 else query
        gallery_2d = gallery.unsqueeze(0) if gallery.ndim == 1 else gallery
        if query_2d.ndim != 2 or gallery_2d.ndim != 2:
            raise ValueError("query and gallery must be [D] or [N, D] tensors")
        if query_2d.shape[1] != gallery_2d.shape[1]:
            raise ValueError(
                f"Embedding dimensions differ: {query_2d.shape[1]} vs {gallery_2d.shape[1]}"
            )

        query_norm = F.normalize(query_2d.float(), p=2, dim=1)
        gallery_norm = F.normalize(gallery_2d.float(), p=2, dim=1)
        return query_norm @ gallery_norm.T

    def _load_model(self, *, verbose: bool) -> nn.Module:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Missing weights: {self.model_path}")

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
            print(f"Loaded {len(matched)} layers from {self.model_path}")
            if discarded:
                print(f"Discarded {len(discarded)} incompatible layers.")

        return model

    @staticmethod
    def _load_state_dict(weight_path: Path) -> OrderedDict[str, Tensor]:
        checkpoint = torch.load(weight_path, map_location="cpu", weights_only=False)
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            checkpoint = checkpoint["state_dict"]
        if not isinstance(checkpoint, dict):
            raise TypeError(f"Unsupported checkpoint type: {type(checkpoint)!r}")

        state_dict = OrderedDict()
        for key, value in checkpoint.items():
            if isinstance(value, Tensor):
                state_dict[key.removeprefix("module.")] = value
        return state_dict

    @classmethod
    def _build_preprocess(cls) -> transforms.Compose:
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
        return self.transform(self._to_pil_image(image, color_format))

    @staticmethod
    def _to_pil_image(image: ImageInput, color_format: ColorFormat) -> Image.Image:
        if isinstance(image, (str, Path)):
            return Image.open(image).convert("RGB")
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        if isinstance(image, np.ndarray):
            if image.ndim != 3 or image.shape[2] != 3:
                raise ValueError(
                    f"Expected numpy image shape [H, W, 3], got {image.shape}"
                )
            array = image[:, :, ::-1] if color_format == "bgr" else image
            return Image.fromarray(array.astype(np.uint8)).convert("RGB")
        raise TypeError(f"Unsupported image input type: {type(image)!r}")

    @staticmethod
    def _pick_device(device: str | torch.device) -> torch.device:
        if isinstance(device, torch.device):
            return device
        if device != "auto":
            return torch.device(device)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")


__all__ = ["ColorFormat", "ImageInput", "OSNetAINEmbedder"]
