"""Attach an exam document without editing results, dates or student levels."""
import io
from pathlib import Path
import uuid
import requests
from django.conf import settings
from django.http import JsonResponse
from . import music_exams as exams
from .access_control import service_headers, user_scope, can_access

MAX_SIZE=12*1024*1024
MIME={'.pdf':'application/pdf','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp'}


def api_attachment(request,record_id):
    if not exams.can_open_module(request):
        return exams.denied()
    if request.method!='POST':
        return JsonResponse({'error':'Método não permitido.'},status=405)
    file=request.FILES.get('prova')
    if not file:
        return JsonResponse({'error':'Escolha uma prova ou carta para anexar.'},status=400)
    extension=Path(file.name).suffix.lower()
    if extension not in MIME or file.size>MAX_SIZE:
        return JsonResponse({'error':'Envie PDF, JPG, PNG ou WebP com até 12 MB.'},status=400)
    try:
        response=requests.get(exams.rest_url(),headers=service_headers(),
            params={'select':'*','id':'eq.'+str(record_id),'limit':1},timeout=(5,15))
        response.raise_for_status();rows=response.json()
        if not rows or not can_access(user_scope(request),{'municipio':rows[0].get('municipio'),'comum':rows[0].get('comum')}):
            return JsonResponse({'error':'Exame não encontrado no seu acesso.'},status=404)
        row=rows[0];content=file.read(MAX_SIZE+1)
        if len(content)>MAX_SIZE:
            return JsonResponse({'error':'O documento deve ter no máximo 12 MB.'},status=400)
        if extension=='.pdf':
            if not content.startswith(b'%PDF-'):
                return JsonResponse({'error':'O arquivo não é um PDF válido.'},status=400)
        else:
            from PIL import Image
            with Image.open(io.BytesIO(content)) as image:
                if image.width*image.height>40_000_000:
                    return JsonResponse({'error':'A imagem deve ter no máximo 40 megapixels.'},status=400)
                image.verify()
        path=f"{row['aluno_id']}/{uuid.uuid4()}{extension}"
        headers={'apikey':settings.SUPABASE_SERVICE_ROLE_KEY,'Authorization':f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
                 'Content-Type':MIME[extension]}
        response=requests.post(f'{settings.SUPABASE_URL}/storage/v1/object/{exams.BUCKET}/{path}',
                               headers=headers,data=content,timeout=(5,40))
        response.raise_for_status()
        params={'id':'eq.'+str(record_id),'municipio':'eq.'+str(row.get('municipio') or '')}
        params['comum']='is.null' if row.get('comum') is None else 'eq.'+row['comum']
        response=requests.patch(exams.rest_url(),headers=service_headers('return=representation'),params=params,
            json={'prova_url':path,'prova_nome':file.name},timeout=(5,20))
        response.raise_for_status();updated=response.json()
        if not updated:
            return JsonResponse({'error':'O exame foi alterado durante o envio. Atualize a lista e confira o documento.'},status=409)
        return JsonResponse({'ok':True,'item':exams.restore_agenda(updated[0])})
    except (ValueError,OSError):
        return JsonResponse({'error':'Não foi possível ler a imagem. Envie PDF, JPG, PNG ou WebP válido.'},status=400)
    except requests.RequestException:
        return JsonResponse({'error':'Não foi possível concluir o anexo. Confira o exame antes de tentar novamente.'},status=502)
