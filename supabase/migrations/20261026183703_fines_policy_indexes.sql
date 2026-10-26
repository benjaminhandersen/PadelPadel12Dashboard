create index padel_fines_reason on public.padel_fines(reason);
alter policy own_membership on public.padel_members
 using (email = lower(((select auth.jwt()) ->> 'email')));
