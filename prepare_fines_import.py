"""Prepare (never automatically execute) a validated one-time source-ledger import."""
import csv
import io
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
from datetime import datetime

SOURCE = '1U8msry9gyfBb6OQ1WhoMjvP0qkjN84kHxcx86OwKs1I'
# Verified against Rankedin's own-team match records, not spreadsheet-created players.
ALIASES = {'Benjamin': 'Benjamin Andersen', 'Jesper': 'Jesper Carlsen',
           'Kasper': 'Kasper Elsborg', 'Iversen': 'Kasper Iversen',
           'Patrick': 'Patrick Antoft-Olsen', 'Rasmus B': 'Rasmus Boisen Brydegaard',
           'Rasmus H': 'Rasmus H.', 'Simon': 'Simon Fischer Olesen',
           'Simon Norlen': 'Simon Norlén', 'Karsten': 'Karsten Scheelke'}


def prepare(text, roster):
    sections = [s for s in text.split('\f') if s.lstrip().startswith(',PADEL · HISTORIK,')]
    if len(sections) != 1:
        raise ValueError('Entydig historikfane mangler')
    by_name = {p['name']: int(p['player_id']) for p in roster}
    result, seen = [], set()
    started = False
    for row in csv.reader(io.StringIO(sections[0])):
        if row[1:4] == ['ID', 'Tidspunkt', 'Spiller']:
            started = True
            continue
        if not started or len(row) < 10 or not row[1]:
            continue
        _, source_id, stamp, short_name, reason, quantity, rate, amount, cancelled, note = row[:10]
        full_name = ALIASES.get(short_name, short_name)
        if full_name not in by_name or source_id in seen or cancelled not in ('True', 'False'):
            raise ValueError(f'Ugyldig eller tvetydig registrering: {source_id} / {short_name}')
        seen.add(source_id)
        quantity, rate, amount = int(quantity), int(rate), int(amount)
        if min(quantity, rate, amount) <= 0 or amount != quantity * rate:
            raise ValueError(f'Beløb stemmer ikke: {source_id}')
        created = datetime.fromisoformat(stamp).replace(tzinfo=ZoneInfo('Europe/Copenhagen')).isoformat() if stamp else None
        identity = SOURCE + ':' + source_id
        result.append(dict(id=str(uuid5(NAMESPACE_URL, identity)), source_id=identity,
                           player_id=by_name[full_name], player=full_name, reason=reason,
                           quantity=quantity, unit_amount=rate, amount=amount,
                           cancelled=cancelled == 'True', created=created, note=note))
    if not result:
        raise ValueError('Historikken er tom')
    return result


def import_sql(rows, roster):
    def quote(value):
        return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    players = list({p['player_id']: {'player_id': p['player_id'], 'name': p['name']} for p in roster}.values())
    return f'''begin;
insert into public.padel_players(player_id,name)
select player_id,name from jsonb_to_recordset({quote(players)}) as p(player_id bigint,name text)
on conflict(player_id) do update set name=excluded.name;
insert into public.padel_fines(id,source_id,player_id,player,reason,quantity,unit_amount,amount,cancelled,created,note)
select id,source_id,player_id,player,reason,quantity,unit_amount,amount,cancelled,created,note
from jsonb_to_recordset({quote(rows)}) as f(id uuid,source_id text,player_id bigint,player text,reason text,
 quantity integer,unit_amount integer,amount integer,cancelled boolean,created timestamptz,note text)
on conflict(source_id) do nothing;
commit;
select count(*) as registrations, count(*) filter(where cancelled) as cancelled,
 sum(quantity) filter(where not cancelled) as active_fines,
 sum(amount) filter(where not cancelled) as total_dkk from public.padel_fines;
'''


if __name__ == '__main__':
    roster = json.loads(Path('data/rankedin_roster.json').read_text(encoding='utf-8'))
    rows = prepare(Path('data/source_fines.txt').read_text(encoding='utf-8'), roster)
    Path('data/import_fines.sql').write_text(import_sql(rows, roster), encoding='utf-8')
    print(json.dumps({'registrations': len(rows), 'cancelled': sum(r['cancelled'] for r in rows),
                      'active_fines': sum(r['quantity'] for r in rows if not r['cancelled']),
                      'total_dkk': sum(r['amount'] for r in rows if not r['cancelled'])}))
