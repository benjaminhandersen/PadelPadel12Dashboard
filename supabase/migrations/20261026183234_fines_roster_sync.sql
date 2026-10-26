create policy admin_players_insert on public.padel_players for insert to authenticated
 with check (exists (select 1 from public.padel_members where role='admin'));
create policy admin_players_update on public.padel_players for update to authenticated
 using (exists (select 1 from public.padel_members where role='admin'))
 with check (exists (select 1 from public.padel_members where role='admin'));
grant insert(player_id,name), update(name) on public.padel_players to authenticated;
create or replace function public.padel_fines_snapshot() returns jsonb
language sql stable security invoker set search_path = '' as $$
 select jsonb_build_object(
  'players', coalesce((select jsonb_agg(p order by p.name) from public.padel_players p),'[]'::jsonb),
  'rules', coalesce((select jsonb_agg(r order by r.amount,r.name) from public.padel_rules r),'[]'::jsonb),
  'fines', coalesce((select jsonb_agg(f order by f.created desc nulls last,f.recorded_at desc,f.id) from public.padel_fines f),'[]'::jsonb),
  'role', (select role from public.padel_members limit 1)
 )
$$;
