-- A single club fund shared across seasonal Rankedin team IDs.
create table public.padel_members (
  email text primary key check (email = lower(email)),
  role text not null check (role in ('member','admin'))
);
create table public.padel_players (
  player_id bigint primary key,
  name text not null check (length(trim(name)) > 0)
);
create table public.padel_rules (
  name text primary key,
  amount integer not null check (amount between 1 and 10000)
);
create table public.padel_fines (
  id uuid primary key default gen_random_uuid(),
  player_id bigint not null references public.padel_players(player_id),
  player text not null,
  reason text not null references public.padel_rules(name),
  quantity integer not null default 1 check (quantity > 0),
  unit_amount integer not null check (unit_amount > 0),
  amount integer not null check (amount = quantity * unit_amount),
  created timestamptz default now(),
  recorded_at timestamptz not null default now(),
  created_by uuid references auth.users(id),
  cancelled boolean not null default false,
  source_id text unique,
  note text not null default ''
);
create index padel_fines_player on public.padel_fines(player_id);
create index padel_fines_created_by on public.padel_fines(created_by);
create index padel_fines_created on public.padel_fines(created desc, id);

alter table public.padel_members enable row level security;
alter table public.padel_players enable row level security;
alter table public.padel_rules enable row level security;
alter table public.padel_fines enable row level security;

-- Membership is administered by the project owner, never from user metadata.
create policy own_membership on public.padel_members for select to authenticated
  using (email = lower((select auth.jwt()->>'email')));
create policy team_players on public.padel_players for select to authenticated
  using (exists (select 1 from public.padel_members));
create policy team_rules on public.padel_rules for select to authenticated
  using (exists (select 1 from public.padel_members));
create policy admin_rules on public.padel_rules for update to authenticated
  using (exists (select 1 from public.padel_members where role='admin'))
  with check (exists (select 1 from public.padel_members where role='admin'));
create policy team_fines_read on public.padel_fines for select to authenticated
  using (exists (select 1 from public.padel_members));
create policy team_fines_insert on public.padel_fines for insert to authenticated
  with check (exists (select 1 from public.padel_members) and created_by = (select auth.uid()));
create policy team_fines_cancel on public.padel_fines for update to authenticated
  using (exists (select 1 from public.padel_members))
  with check (exists (select 1 from public.padel_members));

-- New entries always use server-side player names, rates and time.
-- Imported historical snapshots are written only by the database owner.
create function public.padel_fine_snapshot() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if current_user = 'authenticated' then
    new.player := (select name from public.padel_players where player_id=new.player_id);
    new.unit_amount := (select amount from public.padel_rules where name=new.reason);
    new.quantity := 1;
    new.amount := new.unit_amount;
    new.created := now();
    new.recorded_at := now();
    new.created_by := auth.uid();
    new.cancelled := false;
    new.source_id := null;
    new.note := '';
  end if;
  return new;
end $$;
revoke all on function public.padel_fine_snapshot() from public, anon, authenticated;
create trigger padel_snapshot_before_insert before insert on public.padel_fines
  for each row execute function public.padel_fine_snapshot();

revoke all on public.padel_members, public.padel_players, public.padel_rules, public.padel_fines from anon, authenticated;
grant select on public.padel_members, public.padel_players, public.padel_rules, public.padel_fines to authenticated;
grant insert (id,player_id,reason) on public.padel_fines to authenticated;
grant update (cancelled) on public.padel_fines to authenticated;
grant update (amount) on public.padel_rules to authenticated;

-- Atomic read: consistent totals/history even while another phone adds a fine.
create function public.padel_fines_snapshot() returns jsonb
language sql stable security invoker set search_path = '' as $$
 select jsonb_build_object(
  'rules', coalesce((select jsonb_agg(r order by r.amount,r.name) from public.padel_rules r),'[]'::jsonb),
  'fines', coalesce((select jsonb_agg(f order by f.created desc nulls last,f.recorded_at desc,f.id) from public.padel_fines f),'[]'::jsonb),
  'role', (select role from public.padel_members limit 1)
 )
$$;
revoke all on function public.padel_fines_snapshot() from public, anon;
grant execute on function public.padel_fines_snapshot() to authenticated;

insert into public.padel_rules(name,amount) values
 ('Dobbeltfejl',10),('For sent til træning',20),('For sent til kamp',50),
 ('Glemt udstyr til træning',20),('Glemt udstyr til kamp',50),('Glemt bat',100),
 ('Glemt holdtrøje til kamp',50),('For sent afbud til kamp',50),
 ('Udeblivelse fra kamp',100),('Tabt sæt 6-0',50);
