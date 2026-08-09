from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.rooms import require_admin
from services.integration_hub_service import (
    IntegrationHubError, public_status, remove_openai, save_openai, test_openai_connection,
    list_integrations, add_integration, update_integration, delete_integration, test_integration,
)

router = APIRouter()

class OpenAISettingsRequest(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=500)
    model: str = Field(default="gpt-5.6", min_length=1, max_length=120)
    enable_piai: bool = True
    enable_game_generation: bool = True

class IntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=40)
    api_key: str = Field(min_length=12, max_length=1000)
    model: str = Field(min_length=1, max_length=120)

class IntegrationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    provider: Optional[str] = Field(default=None, max_length=40)
    api_key: Optional[str] = Field(default=None, max_length=1000)
    model: Optional[str] = Field(default=None, max_length=120)
    enabled: Optional[bool] = None


def _call(fn, *args, **kwargs):
    try: return fn(*args, **kwargs)
    except IntegrationHubError as error: raise HTTPException(status_code=422, detail=str(error))

@router.get('/api/admin/integrations')
def integrations_list(request: Request):
    require_admin(request); return {'items': list_integrations()}

@router.post('/api/admin/integrations', status_code=201)
def integrations_add(data: IntegrationCreate, request: Request):
    require_admin(request); return _call(add_integration, data.name, data.provider, data.api_key, data.model)

@router.patch('/api/admin/integrations/{integration_id}')
def integrations_update(integration_id: int, data: IntegrationUpdate, request: Request):
    require_admin(request); return _call(update_integration, integration_id, **data.dict(exclude_unset=True))

@router.post('/api/admin/integrations/{integration_id}/test')
def integrations_test(integration_id: int, request: Request):
    require_admin(request); return _call(test_integration, integration_id)

@router.delete('/api/admin/integrations/{integration_id}', status_code=204)
def integrations_delete(integration_id: int, request: Request):
    require_admin(request); delete_integration(integration_id); return None

@router.get('/api/admin/integrations/openai')
def openai_status(request: Request): require_admin(request); return public_status()

@router.put('/api/admin/integrations/openai')
def openai_save(data: OpenAISettingsRequest, request: Request):
    require_admin(request); return _call(save_openai, data.api_key, data.model, data.enable_piai, data.enable_game_generation)

@router.post('/api/admin/integrations/openai/test')
def openai_test(request: Request): require_admin(request); return _call(test_openai_connection)

@router.delete('/api/admin/integrations/openai')
def openai_remove(request: Request): require_admin(request); return remove_openai()
