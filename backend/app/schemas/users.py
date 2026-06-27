from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Tower1Profile(BaseModel):
    # Universal Dimensions (Apply to all readers)
    darkness_tolerance: Optional[float] = Field(None, ge=0.0, le=1.0)
    angst_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    violence_tolerance: Optional[float] = Field(None, ge=0.0, le=1.0)
    thematic_density: Optional[float] = Field(None, ge=0.0, le=1.0)
    pacing_preference: Optional[float] = Field(None, ge=0.0, le=1.0)
    prose_density: Optional[float] = Field(None, ge=0.0, le=1.0)
    narrative_linearity: Optional[float] = Field(None, ge=0.0, le=1.0)
    plot_vs_character: Optional[float] = Field(None, ge=0.0, le=1.0)
    setting_scope: Optional[float] = Field(None, ge=0.0, le=1.0)
    speculative_deviation: Optional[float] = Field(None, ge=0.0, le=1.0)
    world_building_appetite: Optional[float] = Field(None, ge=0.0, le=1.0)
    emotional_intensity: Optional[float] = Field(None, ge=0.0, le=1.0)
    standalone_preference: Optional[float] = Field(None, ge=0.0, le=1.0)
    series_completion_tendency: Optional[float] = Field(None, ge=0.0, le=1.0)
    reread_tendency: Optional[float] = Field(None, ge=0.0, le=1.0)
    exploration_tolerance: Optional[float] = Field(None, ge=0.0, le=1.0)
    pov_structure: Optional[float] = Field(None, ge=0.0, le=1.0)
    protagonist_agency: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Non-Fiction Conditional Fields
    factual_density: Optional[float] = Field(None, ge=0.0, le=1.0)
    instructional_vs_conceptual: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Romance Conditional Fields
    explicit_content_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    romance_centrality: Optional[float] = Field(None, ge=0.0, le=1.0)
    hea_requirement: Optional[float] = Field(None, ge=0.0, le=1.0)
    relationship_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    role_rigidity: Optional[float] = Field(None, ge=0.0, le=1.0)
    relationship_pace: Optional[float] = Field(None, ge=0.0, le=1.0)

    model_config = ConfigDict(from_attributes=True)
