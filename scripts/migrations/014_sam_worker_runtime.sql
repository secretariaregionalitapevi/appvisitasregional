-- Estado operacional real do worker SAM.
-- Separa o comando solicitado pelo administrador do processo efetivamente ativo.
alter table public.sam_sync_control
    add column if not exists worker_status text not null default 'offline';

alter table public.sam_sync_control
    add column if not exists last_error text;

alter table public.sam_sync_control
    add column if not exists cycle_started_at timestamptz;

comment on column public.sam_sync_control.desired_state is
'Comando administrativo solicitado pelo frontend; não comprova que o worker esteja em execução.';

comment on column public.sam_sync_control.worker_status is
'Estado informado pelo worker: offline, paused, starting, running, idle ou error.';

comment on column public.sam_sync_control.heartbeat_at is
'Último sinal de vida do worker. O painel considera o serviço indisponível quando o sinal fica obsoleto.';
