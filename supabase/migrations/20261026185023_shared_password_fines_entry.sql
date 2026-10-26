-- The shared-password app authorizes access on its Python server.
-- This function is unavailable to public clients and individual-user JWTs.
create function public.padel_give_shared_fine(p_id uuid, p_player_id bigint, p_reason text)
returns setof public.padel_fines
language plpgsql security invoker set search_path = '' as $$
begin
 insert into public.padel_fines(id,player_id,player,reason,quantity,unit_amount,amount)
 select p_id,p.player_id,p.name,r.name,1,r.amount,r.amount
 from public.padel_players p cross join public.padel_rules r
 where p.player_id=p_player_id and r.name=p_reason
 on conflict(id) do nothing;
 return query select f.* from public.padel_fines f
 where f.id=p_id and f.player_id=p_player_id and f.reason=p_reason;
end $$;
revoke all on function public.padel_give_shared_fine(uuid,bigint,text) from public, anon, authenticated;
grant execute on function public.padel_give_shared_fine(uuid,bigint,text) to service_role;
