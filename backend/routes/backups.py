from __future__ import annotations

from urllib.parse import quote
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Optional

from routes.rooms import require_admin
from services.backup_manager_service import (
    BACKUPS_DIR, _backup_path, accounts_csv, add_upload_file, backup_info, create_backup,
    delete_backup, duplicate_backup, import_backup, inspect_backup, list_backups,
    remove_upload_file, rename_backup, restore_backup, update_metadata, validate_backup, read_backup_upload,
)
from connection_manager import manager

router=APIRouter(prefix='/api/admin/backups',tags=['backups'])

class CreatePayload(BaseModel):
    label:str=''; note:str=''
class MetadataPayload(BaseModel):
    label:str=''; note:str=''
class RenamePayload(BaseModel):
    new_name:str=Field(min_length=1,max_length=140)
class DuplicatePayload(BaseModel):
    new_name:Optional[str]=None
class RestorePayload(BaseModel):
    confirmation:str
class MemberPayload(BaseModel):
    path:str

def admin(request:Request): return require_admin(request)
def fail(exc):
    if isinstance(exc,FileNotFoundError): return HTTPException(404,str(exc))
    if isinstance(exc,FileExistsError): return HTTPException(409,str(exc))
    return HTTPException(422,str(exc))

@router.get('')
def backups(request:Request): admin(request); return list_backups()

@router.post('')
def create(data:CreatePayload,request:Request):
    u=admin(request)
    try: p=create_backup(data.label,data.note); return backup_info(p)
    except Exception as e: raise fail(e)

@router.post('/import')
def import_zip(request:Request,file:UploadFile=File(...)):
    admin(request)
    try: return import_backup(file.file,file.filename or 'backup.zip')
    except Exception as e: raise fail(e)

@router.get('/{name}/download')
def download(name:str,request:Request):
    admin(request)
    try: p=_backup_path(name); validate_backup(p)
    except Exception as e: raise fail(e)
    return FileResponse(p,media_type='application/zip',filename=p.name)

@router.get('/{name}/accounts.csv')
def export_accounts(name:str,request:Request):
    admin(request)
    try: data=accounts_csv(name)
    except Exception as e: raise fail(e)
    filename=f"{name.rsplit('.',1)[0]}_comptes.csv"
    return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(filename)}"})

@router.get('/{name}/files/{member:path}')
def extract_file(name:str,member:str,request:Request):
    admin(request)
    try:
        item=read_backup_upload(name,'uploads/'+member.lstrip('/'))
        return Response(item['data'],media_type=item['mime'],headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(item['name'])}"})
    except Exception as e: raise fail(e)

@router.get('/{name}')
def inspect(name:str,request:Request):
    admin(request)
    try: return inspect_backup(name)
    except Exception as e: raise fail(e)

@router.patch('/{name}')
def metadata(name:str,data:MetadataPayload,request:Request):
    admin(request)
    try: return update_metadata(name,data.label,data.note)
    except Exception as e: raise fail(e)

@router.post('/{name}/rename')
def rename(name:str,data:RenamePayload,request:Request):
    admin(request)
    try: return rename_backup(name,data.new_name)
    except Exception as e: raise fail(e)

@router.post('/{name}/duplicate')
def duplicate(name:str,data:DuplicatePayload,request:Request):
    admin(request)
    try: return duplicate_backup(name,data.new_name)
    except Exception as e: raise fail(e)

@router.post('/{name}/validate')
def validate(name:str,request:Request):
    admin(request)
    try: p=_backup_path(name); result=validate_backup(p); return {'valid':True,'manifest':result['manifest']}
    except Exception as e: raise fail(e)

@router.post('/{name}/files')
def add_file(name:str,request:Request,file:UploadFile=File(...)):
    admin(request)
    try: return add_upload_file(name,file.file,file.filename or 'fichier')
    except Exception as e: raise fail(e)

@router.delete('/{name}/files')
def remove_file(name:str,data:MemberPayload,request:Request):
    admin(request)
    try: return remove_upload_file(name,data.path)
    except Exception as e: raise fail(e)

@router.post('/{name}/restore')
async def restore(name:str,data:RestorePayload,request:Request):
    admin(request)
    if data.confirmation.strip().upper()!='RESTAURER': raise HTTPException(422,'Tape RESTAURER pour confirmer.')
    try:
        await manager.disconnect_all('Restauration d’une sauvegarde en cours…')
        return restore_backup(name)
    except Exception as e: raise fail(e)

@router.delete('/{name}')
def delete(name:str,request:Request):
    admin(request)
    try: delete_backup(name); return {'deleted':name}
    except Exception as e: raise fail(e)
