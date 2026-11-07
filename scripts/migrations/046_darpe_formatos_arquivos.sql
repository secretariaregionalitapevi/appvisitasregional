-- Ampliar formatos mantendo o bucket privado e o limite de 20 MB.
begin;
update storage.buckets set public=false, file_size_limit=20971520,
allowed_mime_types=array['application/pdf','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.presentationml.presentation','application/vnd.ms-excel','application/msword','application/vnd.ms-powerpoint','image/jpeg','image/png','image/webp','image/gif','text/plain','text/csv']
where id='darpe-documentos';
commit;
