from __future__ import annotations

from typing import Literal, Annotated
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict, model_validator


def uid():
    return uuid4().hex


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Bubble(StrictModel):
    speaker: str = Field(default='', max_length=100)
    text: str = Field(min_length=1, max_length=220)
    side: Literal['left', 'right'] = 'right'
    vertical: Literal['top', 'bottom'] = 'top'
    shape: Literal['speech', 'thought', 'whisper', 'shout'] = 'speech'
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    width: float | None = Field(default=None, ge=.08, le=1)
    height: float | None = Field(default=None, ge=.025, le=1)
    tail_x: float | None = Field(default=None, ge=0, le=1)
    tail_y: float | None = Field(default=None, ge=0, le=1)
    show_tail: bool = True
    font_size: float = Field(default=10, ge=8, le=18)

    @model_validator(mode='after')
    def bounded_frame(self):
        if self.x is not None and self.width is not None and self.x+self.width > 1.001:
            raise ValueError('Sprechblase reicht rechts über das Panel hinaus.')
        if self.y is not None and self.height is not None and self.y+self.height > 1.001:
            raise ValueError('Sprechblase reicht unten über das Panel hinaus.')
        return self


PoseText = Annotated[str, Field(max_length=800)]


class Panel(StrictModel):
    id: str = Field(default_factory=uid, pattern='^[a-f0-9]{32}$')
    description: str = Field(min_length=1, max_length=1200)
    visual_prompt: str = Field(min_length=1, max_length=2500)
    shot: Literal['wide', 'medium', 'close', 'detail'] = 'medium'
    emphasis: Literal['normal', 'wide', 'tall', 'splash'] = 'normal'
    beat: Literal['establishing', 'action', 'reaction', 'detail', 'reveal'] = 'action'
    page_break_before: bool = False
    page_break_after: bool = False
    border: Literal['framed', 'open'] = 'framed'
    characters: list[str] = Field(default_factory=list, max_length=4)
    character_poses: dict[str, PoseText] = Field(default_factory=dict, max_length=4)
    bubbles: list[Bubble] = Field(default_factory=list, max_length=4)
    caption: str = Field(default='', max_length=160)
    focus_x: float = Field(default=.5, ge=0, le=1)
    focus_y: float = Field(default=.45, ge=0, le=1)
    image: str = ''
    image_signature: str = ''


class Scene(StrictModel):
    id: str = Field(default_factory=uid, pattern='^[a-f0-9]{32}$')
    title: str = Field(min_length=1, max_length=160)
    location: str = Field(default='', max_length=250)
    rhythm: Literal['calm', 'action', 'reveal'] = 'calm'
    layout: Literal['auto', 'balanced', 'dynamic', 'cinematic', 'full_bleed'] = 'auto'
    layout_reason: str = Field(default='', max_length=500)
    source_start: int = Field(ge=1)
    source_end: int = Field(ge=1)
    source_excerpt: str = Field(min_length=8, max_length=600)
    panels: list[Panel] = Field(min_length=1, max_length=6)


class PlanChunk(StrictModel):
    summary: str = Field(min_length=1, max_length=1800)
    scenes: list[Scene] = Field(min_length=1, max_length=4)


class CharacterInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    aliases: str = Field(default='', max_length=300)


class BookSettings(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    style: str = Field(default='Black and white dark fantasy manga, expressive ink line art, screentones, consistent character designs, cinematic lighting.', min_length=1, max_length=1500)
    direction: Literal['rtl', 'ltr'] = 'rtl'
    monochrome: bool = True


class Settings(StrictModel):
    comfy_url: str = 'http://127.0.0.1:8188'
    text_model: str = 'qwen3.5_4b_bf16.safetensors'
    vision_model: str = 'qwen3vl_4b_fp8_scaled.safetensors'
    image_model: str = 'flux-2-klein-4b-fp8.safetensors'
    image_encoder: str = 'qwen_3_4b.safetensors'
    image_vae: str = 'full_encoder_small_decoder.safetensors'
    timeout: int = Field(default=1800, ge=60, le=7200)


class EditPlan(StrictModel):
    revision: int = Field(ge=0)
    scenes: list[Scene] = Field(max_length=300)


class GenerateRequest(StrictModel):
    panel_id: str | None = None
    missing_only: bool = True


class ExportRequest(StrictModel):
    draft: bool = False


class PlanRequest(StrictModel):
    replace: bool = False


class CharacterAnalysis(StrictModel):
    description: str = Field(min_length=20, max_length=1600)
    observations: str = Field(min_length=10, max_length=1400)
    uncertainty: str = Field(default='', max_length=500)


class AcceptCharacterRender(StrictModel):
    image: str = Field(min_length=1, max_length=500)
    use_description: bool = False


class DetectedCharacter(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    description: str = Field(min_length=10, max_length=1800)
    kind: Literal['named', 'role'] = 'named'
    source_start: int = Field(ge=1)
    source_end: int = Field(ge=1)
    mention: str = Field(min_length=1, max_length=120)


class CharacterDiscovery(StrictModel):
    characters: list[DetectedCharacter] = Field(default_factory=list, max_length=40)
