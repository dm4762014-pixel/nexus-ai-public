from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Format = Literal['pdf', 'docx', 'xlsx', 'pptx', 'csv', 'txt', 'json']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=48, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=128)


class TaskRequest(StrictModel):
    prompt: str = Field(min_length=3, max_length=4000)
    mode: Literal['auto', 'research', 'document', 'code', 'browser', 'chat'] = 'auto'
    formats: list[Format] = Field(default_factory=list, max_length=7)
    upload_ids: list[str] = Field(default_factory=list, max_length=3)
    parent_task_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def followup_modes(self):
        if self.parent_task_id and self.mode not in ('auto', 'chat', 'document'):
            raise ValueError('Follow-ups support answers and documents. Start a new task for research, browser or code tools.')
        return self

    @field_validator('upload_ids')
    @classmethod
    def ids(cls, values):
        import re
        if any(not re.fullmatch(r'[a-f0-9]{32}', v) for v in values):
            raise ValueError('Invalid upload ID')
        return list(dict.fromkeys(values))


class Plan(StrictModel):
    research: bool = False
    browser_url: str | None = Field(default=None, max_length=2048)
    browser_urls: list[Annotated[str, Field(min_length=1, max_length=2048)]] = Field(default_factory=list, max_length=3)
    code: bool = False
    formats: list[Format] = Field(default_factory=list, max_length=7)
    title: str = Field(default='NEXUS AI task', min_length=1, max_length=120)

    @model_validator(mode='after')
    def browser_destinations(self):
        self.browser_urls = list(dict.fromkeys(self.browser_urls))
        if self.browser_urls:
            if self.browser_url and self.browser_url != self.browser_urls[0]:
                raise ValueError('The initial browser URL must match the first approved page')
            self.browser_url = self.browser_urls[0]
        return self


class ScheduleRequest(StrictModel):
    prompt: str = Field(min_length=3, max_length=4000)
    interval_minutes: int = Field(ge=15, le=525600)


class ScheduleState(StrictModel):
    enabled: bool = Field(strict=True)


class Decision(StrictModel):
    approved: bool
