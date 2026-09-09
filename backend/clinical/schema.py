from pydantic import BaseModel, Field


class Symptom(BaseModel):
    name: str = Field(
        description="The symptom explicitly reported by the patient."
    )
    duration: str | None = Field(
        default=None,
        description="How long the symptom has been present."
    )
    severity: str | None = Field(
        default=None,
        description="Severity if explicitly mentioned by the patient."
    )
    location: str | None = Field(
        default=None,
        description="Body location if explicitly mentioned."
    )
    radiation: str | None = Field(
        default=None,
        description="Where the symptom radiates or spreads, if explicitly mentioned."
    )
    aggravating_factors: list[str] = Field(
        default_factory=list,
        description="Things that make the symptom worse."
    )
    relieving_factors: list[str] = Field(
        default_factory=list,
        description="Things that make the symptom better."
    )
    associated_symptoms: list[str] = Field(
        default_factory=list,
        description="Other symptoms mentioned in association."
    )
    present: bool = Field(
        default=True,
        description="Whether the patient currently reports this symptom."
    )


class ClinicalExtraction(BaseModel):
    chief_complaint: str | None = Field(default=None)
    symptoms: list[Symptom] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    past_medical_history: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)


# -------------------------
# Normalized schemas
# -------------------------

class NormalizedSymptom(BaseModel):
    name: str
    duration: str | None = None
    severity: str | None = None
    location: str | None = None
    radiation: str | None = None
    aggravating_factors: list[str] = Field(default_factory=list)
    relieving_factors: list[str] = Field(default_factory=list)
    associated_symptoms: list[str] = Field(default_factory=list)
    present: bool = True


class NormalizedClinicalData(BaseModel):
    chief_complaint: str | None = None
    symptoms: list[NormalizedSymptom] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    past_medical_history: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)