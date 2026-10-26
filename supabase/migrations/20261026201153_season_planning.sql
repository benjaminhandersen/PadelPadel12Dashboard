-- The Streamlit server verifies shared login. No browser
-- role may read/write these tables or execute their RPCs directly.
create table public.padel_planning_polls (
 id uuid primary key,
 season_key text not null check (length(trim(season_key)) between 1 and 150),
 title text not null check (length(trim(title)) between 1 and 150),
 slots jsonb not null check (jsonb_typeof(slots) = 'array' and jsonb_array_length(slots) between 1 and 100),
 deadline date,
 status text not null default 'open' check (status in ('open','closed','final','archived')),
 final_slot uuid,
 version integer not null default 1,
 updated_at timestamptz not null default now(),
 check ((status = 'final') = (final_slot is not null))
);
create index padel_planning_season_idx on public.padel_planning_polls(season_key);
create table public.padel_planning_votes (
 poll_id uuid not null references public.padel_planning_polls(id),
 player_id bigint not null references public.padel_players(player_id),
 answers jsonb not null check (jsonb_typeof(answers) = 'object'),
 version integer not null default 1,
 updated_at timestamptz not null default now(),
 primary key (poll_id,player_id)
);
create index padel_planning_player_idx on public.padel_planning_votes(player_id);
alter table public.padel_planning_polls enable row level security;
alter table public.padel_planning_votes enable row level security;
revoke all on public.padel_planning_polls,public.padel_planning_votes from public,anon,authenticated;
grant select,insert,update on public.padel_planning_polls,public.padel_planning_votes to service_role;

create function public.padel_planning_snapshot(p_season text) returns jsonb
language sql stable security invoker set search_path = '' as $$
 select jsonb_build_object(
  'players',coalesce((select jsonb_agg(p order by p.name,p.player_id) from public.padel_players p),'[]'::jsonb),
  'polls',coalesce((select jsonb_agg(p order by p.updated_at desc,p.id) from public.padel_planning_polls p where p.season_key=p_season),'[]'::jsonb),
  'votes',coalesce((select jsonb_agg(v order by v.poll_id,v.player_id) from public.padel_planning_votes v
    join public.padel_planning_polls p on p.id=v.poll_id where p.season_key=p_season),'[]'::jsonb)
 )
$$;

create function public.padel_planning_save_poll(
 p_id uuid,p_season text,p_title text,p_slots jsonb,p_deadline date,
 p_status text,p_final_slot uuid,p_version integer) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare existing public.padel_planning_polls; saved public.padel_planning_polls; slot jsonb;
begin
 if jsonb_typeof(p_slots) is distinct from 'array' or jsonb_array_length(p_slots) not between 1 and 100 then
  raise exception 'Invalid slots';
 end if;
 for slot in select value from jsonb_array_elements(p_slots) loop
  if slot->>'id' is null or slot->>'starts_at' is null then raise exception 'Invalid slot'; end if;
  perform (slot->>'id')::uuid;
  perform (slot->>'starts_at')::timestamp;
 end loop;
 if (select count(distinct value->>'id') from jsonb_array_elements(p_slots)) <> jsonb_array_length(p_slots)
  or (select count(distinct (value->>'starts_at')::timestamp) from jsonb_array_elements(p_slots)) <> jsonb_array_length(p_slots) then
  raise exception 'Duplicate slots';
 end if;
 if p_final_slot is not null and not exists(select 1 from jsonb_array_elements(p_slots) s where (s->>'id')::uuid=p_final_slot) then
  raise exception 'Unknown final slot';
 end if;
 -- An existing option's ID may never be reused for a different time: doing so
 -- would make old availability answers refer to a new date without consent.
 select * into existing from public.padel_planning_polls where id=p_id for update;
 if found then
  if existing.version <> p_version or existing.season_key <> p_season then raise exception 'Stale poll'; end if;
  if exists(select 1 from jsonb_array_elements(existing.slots) old_slot
    join jsonb_array_elements(p_slots) new_slot on old_slot->>'id'=new_slot->>'id'
    where (old_slot->>'starts_at')::timestamp <> (new_slot->>'starts_at')::timestamp) then
   raise exception 'Cannot reuse a slot ID for a new time';
  end if;
  update public.padel_planning_polls set title=trim(p_title),slots=p_slots,deadline=p_deadline,
   status=p_status,final_slot=p_final_slot,version=version+1,updated_at=now()
   where id=p_id returning * into saved;
 else
  if p_version <> 0 then raise exception 'Missing poll'; end if;
  insert into public.padel_planning_polls(id,season_key,title,slots,deadline,status,final_slot)
   values(p_id,p_season,trim(p_title),p_slots,p_deadline,p_status,p_final_slot) returning * into saved;
 end if;
 return to_jsonb(saved);
end $$;

create function public.padel_planning_save_vote(
 p_poll uuid,p_player bigint,p_answers jsonb,p_poll_version integer,p_version integer) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare poll public.padel_planning_polls; saved public.padel_planning_votes;
begin
 -- Serialize editing/finalizing and voting so nobody answers an obsolete poll.
 select * into poll from public.padel_planning_polls where id=p_poll for update;
 if not found or poll.version <> p_poll_version or poll.status <> 'open'
  or (poll.deadline is not null and poll.deadline < (now() at time zone 'Europe/Copenhagen')::date) then
  raise exception 'Poll changed or closed';
 end if;
 if jsonb_typeof(p_answers) is distinct from 'object' then raise exception 'Invalid answers'; end if;
 if (select count(*) from jsonb_object_keys(p_answers)) <> jsonb_array_length(poll.slots)
  or exists(select 1 from jsonb_each(p_answers) a where jsonb_typeof(a.value)<>'boolean'
   or not exists(select 1 from jsonb_array_elements(poll.slots) s where s->>'id'=a.key)) then
  raise exception 'Answer every current slot';
 end if;
 insert into public.padel_planning_votes(poll_id,player_id,answers)
 select p_poll,p_player,p_answers where p_version=0
 on conflict(poll_id,player_id) do nothing returning * into saved;
 if saved.poll_id is null then
  update public.padel_planning_votes set answers=p_answers,version=version+1,updated_at=now()
  where poll_id=p_poll and player_id=p_player and version=p_version returning * into saved;
 end if;
 if saved.poll_id is null then raise exception 'Stale answer'; end if;
 return to_jsonb(saved);
end $$;

revoke all on function public.padel_planning_snapshot(text) from public,anon,authenticated;
revoke all on function public.padel_planning_save_poll(uuid,text,text,jsonb,date,text,uuid,integer) from public,anon,authenticated;
revoke all on function public.padel_planning_save_vote(uuid,bigint,jsonb,integer,integer) from public,anon,authenticated;
grant execute on function public.padel_planning_snapshot(text) to service_role;
grant execute on function public.padel_planning_save_poll(uuid,text,text,jsonb,date,text,uuid,integer) to service_role;
grant execute on function public.padel_planning_save_vote(uuid,bigint,jsonb,integer,integer) to service_role;
