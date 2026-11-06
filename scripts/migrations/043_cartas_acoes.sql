-- Ações do painel: exclusão lógica, concorrência e autoria auditável.
begin;
alter table public.cartas_emissoes add column if not exists deleted_at timestamptz;
alter table public.cartas_emissoes add column if not exists deleted_by uuid;
alter table public.cartas_emissoes add column if not exists deleted_name text;
alter table public.cartas_ministerio_comuns add column if not exists deleted_at timestamptz;
alter table public.cartas_ministerio_comuns add column if not exists managed_by uuid;
alter table public.cartas_ministerio_comuns add column if not exists managed_name text;
alter table public.cartas_ministerio_comuns add column if not exists manage_version integer not null default 1;
alter table public.cartas_emissoes drop constraint if exists cartas_emissoes_duplicate_key_key;
create unique index if not exists cartas_duplicate_active on public.cartas_emissoes(duplicate_key) where deleted_at is null;
create or replace function public.cartas_excluir(p_carta uuid,p_version integer,p_actor uuid,p_nome text)
returns void language plpgsql security definer set search_path=public as $$
declare c public.cartas_emissoes;
begin
 if p_actor is null or nullif(trim(p_nome),'') is null then raise exception 'Usuário inválido'; end if;
 select * into c from public.cartas_emissoes where id=p_carta and deleted_at is null for update;
 if not found then raise exception 'Carta não encontrada'; end if;
 if c.review_version<>p_version then raise exception 'Carta atualizada por outro usuário. Atualize o painel.' using errcode='40001'; end if;
 if c.status<>'ready' then raise exception 'Aguarde o fim da emissão da carta'; end if;
 -- O snapshot auditado preserva também o exame que será retirado das contagens.
 insert into public.cartas_auditoria(carta_id,created_by,owner_session,action,before_data,after_data)
 values(c.id,p_actor,c.owner_session,'DELETE',jsonb_build_object('carta',to_jsonb(c),'exame',
 (select to_jsonb(e) from public.musica_exames_individuais e where e.id=c.exam_id)),jsonb_build_object('actor',p_nome));
 update public.cartas_emissoes set deleted_at=now(),deleted_by=p_actor,deleted_name=p_nome,
 review_version=review_version+1,exam_id=null where id=c.id;
 if c.exam_id is not null and not exists(select 1 from public.cartas_emissoes where exam_id=c.exam_id and deleted_at is null) then
  delete from public.musica_exames_lancamentos where id=c.exam_id;
  delete from public.musica_exames_individuais where id=c.exam_id;
 end if;
end $$;
create or replace function public.cartas_gerir_ministerio(p_codigo text,p_version integer,p_actor uuid,p_nome text,p_values jsonb,p_excluir boolean)
returns jsonb language plpgsql security definer set search_path=public as $$
declare m public.cartas_ministerio_comuns;
begin
 if p_actor is null or nullif(trim(p_nome),'') is null then raise exception 'Usuário inválido'; end if;
 select * into m from public.cartas_ministerio_comuns where common_code=p_codigo and deleted_at is null for update;
 if not found then raise exception 'Relação não encontrada'; end if;
 if m.manage_version<>p_version then raise exception 'Relação atualizada por outro usuário. Atualize o painel.' using errcode='40001'; end if;
 update public.cartas_ministerio_comuns set
 anciao=case when p_excluir then anciao else p_values->>'anciao' end,
 cooperador=case when p_excluir then cooperador else p_values->>'cooperador' end,
 regional=case when p_excluir then regional else p_values->>'regional' end,
 encarregado=case when p_excluir then encarregado else p_values->>'encarregado' end,
 secretario=case when p_excluir then secretario else p_values->>'secretario' end,
 deleted_at=case when p_excluir then now() else null end,managed_by=p_actor,managed_name=p_nome,
 manage_version=manage_version+1 where common_code=m.common_code returning * into m;
 return to_jsonb(m);
end $$;
revoke all on function public.cartas_excluir(uuid,integer,uuid,text) from public,anon,authenticated;
grant execute on function public.cartas_excluir(uuid,integer,uuid,text) to service_role;
revoke all on function public.cartas_gerir_ministerio(text,integer,uuid,text,jsonb,boolean) from public,anon,authenticated;
grant execute on function public.cartas_gerir_ministerio(text,integer,uuid,text,jsonb,boolean) to service_role;
notify pgrst,'reload schema';
commit;