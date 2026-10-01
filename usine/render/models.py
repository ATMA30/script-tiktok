"""Schémas pydantic des plans renvoyés par le Director Agent (Gemini)."""

from pydantic import BaseModel, Field
from typing import List


class LottieOverlaySpec(BaseModel):
    asset_id: str = Field(
        description="ID of the Lottie asset to play. Must exactly match one of the IDs listed in the LOTTIE LIBRARY catalog."
    )
    in_time: float = Field(
        description="Relative timestamp in seconds within this scene (0.0 = scene start) when the overlay starts."
    )
    duration: float = Field(
        description="Playback duration in seconds. Use 0 to fall back to the asset's natural duration. Keep < scene length."
    )
    x_pct: float = Field(
        description="Horizontal center of the overlay in percent of frame width (0 left, 50 center, 100 right)."
    )
    y_pct: float = Field(
        description="Vertical center of the overlay in percent of frame height (0 top, 50 center, 100 bottom)."
    )
    width_pct: float = Field(
        description="Width of the overlay in percent of frame width. 100 = full width. Use ~30-60 for accents."
    )
    height_pct: float = Field(
        description="Height of the overlay in percent of frame height. Match width_pct for square assets, 100 for full-screen sweeps."
    )
    opacity: float = Field(
        description="Opacity 0.0-1.0. Atmospheric overlays: 0.4-0.7. Punctual reveals: 0.8-1.0."
    )
    monochrome: bool = Field(
        description="Whether to force grayscale to match the cinema true-crime palette. Almost always true."
    )
    reason: str = Field(
        description="One short sentence (<= 100 chars) explaining why this overlay punctuates this exact narration moment."
    )


class SceneDirectorPlan(BaseModel):
    strategy: str = Field(
        description="Visual strategy chosen for this scene (e.g. dramatic push-in, dark grid background, technical scanning)."
    )
    background_effect: str = Field(
        description="Procedural background type: 'mesh', 'lines', 'topo', 'dotgrid', 'scanline', or 'minimal'."
    )
    camera_move: str = Field(
        description="Camera motion style: 'dolly_in', 'dolly_out', 'pan_left', 'pan_right', 'zoom_pan', or 'static'."
    )
    glitch_triggers: List[float] = Field(
        description="Relative timestamps (in seconds, e.g., 1.5, 3.2, between 0.0 and scene duration) when digital glitch interference triggers. Return empty list if no glitch is needed."
    )
    vignette_intensity: float = Field(
        description="Intensity multiplier for vignette, from 0.7 (lighter) to 1.3 (darker/vignette heavy)."
    )
    hud_effect: str = Field(
        description="HUD style overlay: 'scanner', 'ticker', 'radar', or 'none'."
    )
    lottie_overlays: List[LottieOverlaySpec] = Field(
        default_factory=list,
        description="0 to 3 Lottie motion-graphic accents to layer on top of this scene. Pick from the LOTTIE LIBRARY only. Use sparingly — one good accent per scene beats three muddled ones. Return [] if the scene is already strong without overlays.",
    )
